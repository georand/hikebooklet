# -*- coding: utf-8 -*-
"""
 HikeBooklet
 author: georand
 source: https://github.com/georand/hikebooklet
 date: 2021
"""

import io, pathlib, logging

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageColor, ImageFont

from config import *

logger=logging.getLogger(__name__)

class TileMap ():
  '''
  Build an opentopo map (OSM) image
  see:
    https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames
    http://tools.geofabrik.de/calc/
  '''
  def __init__(self, llBox, myCache, resolution = RESOLUTION):
    '''
    llBox : [{'lat':NW_lat,'lon':NW_lon},{'lat':SE_lat,'lon':SE_lon}] (in degree)

    resolution(nbPixels) : resolution of the larger side of the bounding box
                           in the resulting map image. The actual size of the
                           map image will therefore be larger.

    cache : the cache directory for the OSM tiles
    '''
    self.mapImg = None

    self.cache = myCache

    # zoom level of the OSM tiles
    self.zoom = self.getZoom(llBox, resolution)

    # compute map scales
    self.scales = self.getScales(llBox, self.zoom)

    # [NW, SE] OSM tile X,Y bounding box
    self.mapBBoxXY = self.getMapBBoxXY(self.llBox)

    # [NW, SE] tiled map lat,lon boundingBox
    self.mapBBoxLL = self.getMapBBoxLL(self.mapBBoxXY)

    # download the tiles and make a map
    self.mapImg = self.getMap()

  def getZoom(self, box, resolution):
    '''
    given lat/lon bounding box and an image resolution
    return the OSM tile zoom level
    see https://wiki.openstreetmap.org/wiki/Zoom_levels
    '''
    N = resolution/256 # pixel tiles are 256x256

    a = np.abs(  np.arcsinh(np.tan(np.radians(box[0]['lat']))) \
               - np.arcsinh(np.tan(np.radians(box[1]['lat']))) )
    zLat = np.log(N*np.pi/a)/np.log(2)+1

    b = np.abs(np.radians(box[1]['lon']) - np.radians(box[0]['lon']))
    zLon = np.log(N*np.pi/b)/np.log(2)+1

    return int(min(zLat,zLon))

  def getScales(self, box, zoom):
    '''
    given lat/lon bounding box
    compute scales (meter/pixel, lat/pixel, lon/pixel) for the map encompassing the given box
    see https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames#Resolution_and_Scale
    '''
    middle = {'lat':(box[0]['lat'] + box[1]['lat'])/2.,
              'lon':(box[0]['lon'] + box[1]['lon'])/2.}
    meterPerPixel = 156543.03 * np.cos(middle['lat']) / (2**zoom)

    tile = self.LLToXY(middle)
    TL = self.XYToLL(tile)
    BR = self.XYToLL({'x':tile['x']+1, 'y':tile['y']+1})

    latPerPixel = (TL['lat']-BR['lat'])/256
    lonPerPixel = (BR['lon']-TL['lon'])/256

    return {'meterPerPixel':meterPerPixel, 'latPerPixel':latPerPixel, 'lonPerPixel':lonPerPixel}

  def getMapBBoxXY(self, box):
    '''
    given lat/lon bounding box
    return the OSM tile_X,tile_Y bounding box of the tiled map
    '''
    TL = self.LLToXY(box[0])
    BR = self.LLToXY(box[1])
    BR = {'x':BR['x']+1, 'y':BR['y']+1}
    return [TL, BR]

  def getMapBBoxLL(self, box):
    '''
    given OSM tile_X,tile_Y bounding box of the tiled map
    return the lat,lon bounding box of the tiled map
    '''
    TL = self.XYToLL(box[0])
    BR = self.XYToLL(box[1])
    return [TL, BR]

  def LLToXY(self, latlon, zoom = None):
    '''
    return tile_X and tile_Y containing the given coordinates at zoom level
    '''
    if not zoom:
      zoom = self.zoom

    lat_rad = np.radians(latlon['lat'])
    n = 2.0 ** zoom
    x = int((latlon['lon'] + 180.0) / 360.0 * n)
    y = int((1.0 - np.arcsinh(np.tan(lat_rad)) / np.pi) / 2.0 * n)

    return {'x':x, 'y':y}

  def XYToLL(self, xyTile, zoom = None):
    '''
    return the coordinates (lat,lon) of the given tile upper left corner
    '''
    if not zoom:
      zoom = self.zoom
    n = 2.0 ** zoom
    lon_deg = xyTile['x'] / n * 360.0 - 180.0
    lat_rad = np.arctan(np.sinh(np.pi * (1 - 2 * xyTile['y'] / n)))
    lat_deg = lat_rad * 180.0 / np.pi
    return {'lat':lat_deg, 'lon':lon_deg}

  def getMap(self):
    '''
    build the map using using tiles downloaded from openTopoMap
    and a cache directory
    '''

    dx = self.mapBBoxXY[1]['x'] - self.mapBBoxXY[0]['x']
    dy = self.mapBBoxXY[1]['y'] - self.mapBBoxXY[0]['y']

    mapImg = Image.new('RGB', (dx*256, dy*256))

    logger.info(f'retrieving {dx*dy} OpenTopoMap tiles at scale {self.zoom}')

    # get the tiles and paste them in the image
    for i in range(0, dx):
      for j in range(0, dy):
        x = self.mapBBoxXY[0]['x'] + i
        y = self.mapBBoxXY[0]['y'] + j

        # try to load tile from cache
        tileCacheFilename = f'OTM-{self.zoom}-{x}-{y}.png'
        tile = self.cache.loadData(tileCacheFilename)

        # if not present in the cache, download the tile and update the cache
        if not tile:
          logger.info(f'downloading OpenTopoMap tile {tileCacheFilename}')
          try:
            with requests.Session() as s:
              r = s.get(URL_MAP.format(self.zoom,x,y))
              r.raise_for_status()
              tile = r.content
              self.cache.saveData(tileCacheFilename, tile)
          except requests.exceptions.HTTPError as e:
            logger.error(f'unable to download OpenTopoMap tile {self.zoom}-{x}-{y} from server (HTTP error: {e.response.status_code})')
            print(e)
            continue

        # paste the tile image in the map
        imgTile = Image.open(io.BytesIO(tile))
        mapImg.paste(imgTile, (i*imgTile.size[0], j*imgTile.size[1]))
        del imgTile

    return mapImg

  def cropMap(self, box):
    '''
    extract the portion of the map corresponding to the given box (lat,lon)
    '''
    # compute the coordinate of the (lat,lon) box in the map
    nBox = ((box[0]['lon'] - self.mapBBoxLL[0]['lon']) / self.scales['lonPerPixel'],
            (self.mapBBoxLL[0]['lat'] - box[0]['lat']) / self.scales['latPerPixel'],
            (box[1]['lon'] - self.mapBBoxLL[0]['lon']) / self.scales['lonPerPixel'],
            (self.mapBBoxLL[0]['lat'] - box[1]['lat']) / self.scales['latPerPixel'])

    return self.mapImg.crop(nBox)

  def drawScale(self):
    draw = ImageDraw.Draw(self.mapImg)

    # compute the best scale representation based on the image m/px scale
    meterPerPixel = self.scales['meterPerPixel']
    targetedPixelLength = 150
    scaleInMeters = int(np.power(10, int(np.log(targetedPixelLength * meterPerPixel) \
                                         / np.log(10))))
    scaleInPixels = int(meterPerPixel * targetedPixelLength / scaleInMeters) \
                    * scaleInMeters / meterPerPixel

    # draw scale segment
    p1 = (self.mapImg.size[0]-20, self.mapImg.size[1]-20)
    p0 = (p1[0]-scaleInPixels, p1[1])
    draw.line([p0,p1], fill=(0,0,0), width=2)

    # write scale
    p = pathlib.Path(__file__).parent
    font = ImageFont.truetype(str(p.joinpath('fonts/FreeMonoBold.ttf')), 20)
    if scaleInMeters < 1000:
      text = f'{scaleInMeters}m'
    else:
      text = f'{scaleInMeters/1000:.1f}km'
    draw.text((p1[0],p1[1] - 4), text, anchor='rb', font=font, fill=(0,0,0))

    del draw

class GPXMap (TileMap):
  '''
  Build an opentopo map (OSM) image and plot GPX tracks
  '''
  def __init__(self, gpx, trackNum = None, resolution = RESOLUTION, cache = None):
    '''
    resolution(nbPixels) : resolution of the larger side of the resulting map image
                           (depends on the given lat/lon bounding box)
    TrackNum: plot the given track or tracks if None
    cache : the cache directory for the OSM tiles
    '''

    self.mapImg = None
    self.gpx = gpx
    self.resolution = resolution
    self.cache = cache

    # get the gpx boudingbox square for the given track number
    self.llBox = gpx.getBoundingBox(trackNum)

    # zoom level of the OSM tiles
    self.zoom = self.getZoom(self.llBox, resolution)

    # compute map scales
    self.scales = self.getScales(self.llBox, self.zoom)

    # reshape the box in order to obtain a square resolutionxresolution image
    # with the track at the center
    self.llBox = self.reshapeBBox(self.llBox)

    # [NW, SE] OSM tile X,Y bounding box
    self.mapBBoxXY = self.getMapBBoxXY(self.llBox)

    # [NW, SE] tiled map lat,lon boundingBox
    self.mapBBoxLL = self.getMapBBoxLL(self.mapBBoxXY)

    # download the tiles and make a map
    self.mapImg = self.getMap()

    # draw the gpx track
    self.drawGPX(trackNum)

    # crop image map according to bounding box
    self.mapImg = self.cropMap(self.llBox)

    # draw scale
    self.drawScale()

  def reshapeBBox(self, box):
    '''
    reshape the box in order to obtain a square resolutionxresolution image
    with the given lat/lon bounding box at the center
    '''
    dx = (self.resolution - (box[1]['lon'] - box[0]['lon']) / self.scales['lonPerPixel']) / 2
    dy = (self.resolution - (box[0]['lat'] - box[1]['lat']) / self.scales['latPerPixel']) / 2
    dlon = dx * self.scales['lonPerPixel']
    dlat = dy * self.scales['latPerPixel']

    nBox= [{'lat':box[0]['lat'] + dlat, 'lon':box[0]['lon'] - dlon},
           {'lat':box[1]['lat'] - dlat, 'lon':box[1]['lon'] + dlon}]

    return nBox


  def drawGPX(self, trackNum):

    trackList = [self.gpx.tracks[trackNum]] if trackNum!=None else self.gpx.tracks

    draw = ImageDraw.Draw(self.mapImg)

    # create the lists of track point in pixels
    ptList = []
    for trk in trackList:
      ptList.append([])
      for tp in trk['trackPoints']:
        ptList[-1].append(((tp['lon'] - self.mapBBoxLL[0]['lon']) \
                           / self.scales['lonPerPixel'],
                           (self.mapBBoxLL[0]['lat'] - tp['lat']) \
                           / self.scales['latPerPixel']))

    # draw a line segment between points
    c = 0
    for l in ptList:
      p0 = l[0]
      for p1 in l[1:]:
        draw.line([p0,p1], fill=COLORS[c], width=5)
        p0 = p1
      c = (c + 1) % len(COLORS)

    # draw a circle at each point
    c = 1
    s = 1
    for l in ptList:
      for p in l:
        draw.ellipse([(p[0]-s,p[1]-s),(p[0]+s,p[1]+s)], fill=COLORS[c])
      c = (c + 1) % len(COLORS)

    del draw
