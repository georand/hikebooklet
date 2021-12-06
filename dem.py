# -*- coding: utf-8 -*-
"""
 HikeBooklet
 author: georand
 source: https://github.com/georand/hikebooklet
 date: 2021
"""

import io,zipfile,struct,logging

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageColor

from config import *

logger=logging.getLogger(__name__)

class SessionWithHeaderRedirection(requests.Session):
  '''
  overriding requests.Session.rebuild_auth to mantain headers when redirected
  to or from the NASA auth host
  code from https://wiki.earthdata.nasa.gov/display/EL/How+To+Access+Data+With+Python
  '''
  AUTH_HOST = 'urs.earthdata.nasa.gov'
  def __init__(self, auth):
    super().__init__()
    self.auth = auth

  def rebuild_auth(self, prepared_request, response):
    headers = prepared_request.headers
    url = prepared_request.url
    if 'Authorization' in headers:
      original_parsed = requests.utils.urlparse(response.request.url)
      redirect_parsed = requests.utils.urlparse(url)
      if (original_parsed.hostname != redirect_parsed.hostname) and \
         redirect_parsed.hostname != self.AUTH_HOST and \
           original_parsed.hostname != self.AUTH_HOST:
        del headers['Authorization']
    return

class DEM ():
  '''
  get elevation for a (latitude,longitude) point using USGS DEM tiles
  '''
  def __init__(self, username=None, password=None, cache = None):
    '''
    username and password : authentification information for the USGS server
                            if None, try to retrieve it from the cache

    cache : the cache directory for the OSM tiles
    '''
    self.cache = cache

    # store USGS auth or try to retrieve it from cache
    if  username and password:
      self.auth = (username, password)
      self.saveAuth(self.auth)
    else:
      self.auth = self.loadAuth()

  def loadAuth(self):
    # try to load the DEM tile from cache
    data = self.cache.loadData('usgs.dat', crypt = True)
    if data:
      data = data.decode('ascii')
      data = tuple(data.split(':'))
    return data

  def saveAuth(self, auth):
    data = self.auth[0]+':'+self.auth[1]
    self.cache.saveData('usgs.dat', data.encode('ascii'), crypt = True)

  def getTile(self, filename):
    '''
    load  DEM tile from the cache directory or download it from USGS
    if not present in the cache
    '''

    # try to find the DEM tile in the cache
    tilePath = self.cache.check(filename)

    # if not present in the cache, download the tile and store it in the cache
    if not tilePath:
      logger.info('downloading DEM tile {filename}')
      url = URL_DEM.format(filename)
      try:
        with SessionWithHeaderRedirection(self.auth) as s:
          r = s.get(url)
          r.raise_for_status()
          tilePath = self.cache.saveData(filename, r.content)
      except requests.exceptions.HTTPError as e:
        logger.error(f'unable to download DEM tile {filename} from server (HTTP error: {e.response.status_code})')

    return tilePath

  def getElevation(self, pointList):
    '''
    get elevation information for a list of points from DEM tiles
    for the sake of speed, all the points belonging to the same tile are batch processed
    '''

    # count the number of point needing to be processed
    Npt = [0 if not 'b' in p or not p['b'] else 1 for p in pointList].count(0)

    if not Npt:
      return

    logger.info(f'retrieving track point elevations')

    while True:
      # retrieve the first point with no elevation information
      tileLat = None
      tileLon = None
      for p in pointList:
        if not 'ele' in p or not p['ele']:
          tileLat = int(p['lat'])
          tileLon = int(p['lon'])
          break
      if not tileLat:
        break

      # get the DEM tile corresponding to the point lat/llon degrees (integer parts)
      tileId = '{}{:02d}{}{:03d}'.format('S' if tileLat < 0 else 'N', tileLat,
                                         'W' if tileLon < 0 else 'E', tileLon)
      tileFilename = DEM_TILE_NAME.format(tileId)
      tilePath = self.getTile(tileFilename)

      if tilePath:
        # open the zip file and get elevation for all point inside  the DEM tile
        with zipfile.ZipFile(tilePath) as z:
          filename = tileFilename[:tileFilename.rfind('.')] # remove .zip
          with z.open(tileId+'.hgt','r') as f:
            tile  = f.read()
            for pt in pointList:
              if int(pt['lat']) == tileLat and int(pt['lon']) == tileLon:
                pt['ele'] = self.computePointElevation(pt, tile)
            del tile
      else:
        # no DEM tile so set elevation to the last elevation value if any, or 1cm
        lastValue = 0.001
        for pt in pointList:
          if not 'ele' in pt or not pt['ele']:
            if int(pt['lat']) == tileLat and int(pt['lon']) == tileLon:
              pt['ele'] = lastValue
          else:
            lastValue = pt['ele']

  def computePointElevation(self, pt, tile):
    '''
    return elevation for the given point using bilinear interpolation of DEM tile data
    DEM data are DEM_RESOLUTION x DEM_RESOLUTION big endian uint16
    '''
    # get coordinate position in the tile
    x = (pt['lon'] % 1) * DEM_RESOLUTION
    y = (1 - pt['lat'] % 1) * DEM_RESOLUTION - 1
    # retrieve neighbors values
    v = [[0,0],[0,0]]
    for i in range(0,2):
      for j in range(0,2):
        xx = min(int(x) + i, DEM_RESOLUTION - 1)
        yy = max(int(y) - j, 0)
        pos = (xx + yy * DEM_RESOLUTION) * 2
        v[i][j] = struct.unpack('>H',tile[pos:pos+2])[0] # uint16  big endian
    # bilinear interpolation between neighbors
    value =  v[0][0] * (1 - x % 1) * (1 - y % 1)\
           + v[0][1] * (x % 1)     * (1 - y % 1)\
           + v[1][0] * (1 - x % 1) * (y % 1)\
           + v[1][1] * (x % 1)     * (y % 1)
    return(round(value))
