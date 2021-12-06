# -*- coding: utf-8 -*-
"""
 HikeBooklet
 author: georand
 source: https://github.com/georand/hikebooklet
 date: 2021
"""

import datetime, pathlib, logging
import xml.etree.ElementTree as ET

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import *

logger=logging.getLogger(__name__)

RADIUS_EQUATOR = 6378137 # radius in meter of the earth at equator
RADIUS_POLE    = 6356752 # radius in meter of the earth at poles

def computeHikingTime(distance, slope, flatSpeed = FLAT_SPEED):
  '''
  Estimate hiking time of a route using Tobler model
  input distance and slope in meter, output in decimal hour
  See https://en.wikipedia.org/wiki/Tobler%27s_hiking_function
  '''
  if abs(distance) < 0.001:
    return 0
  # speed ratio to be applied to the default flat speed for tobler method (5km/h)
  ratio = flatSpeed/5.
  distance /= 1000. # -> km
  slope /= 1000. # -> km
  speed = (6*np.exp(-3.5*np.abs(slope/distance+0.05)))
  hours = distance/speed/ratio
  return hours

def computeDistance(pt1, pt2, earthRadius = None):
  '''
  Compute distance between two points using the haversine formula
  input ['lon:lon','lat':lat] in WGS84 signed decimal degrees
  output distance in meter
  see https://www.movable-type.co.uk/scripts/latlong.html
  '''
  lat1 = np.radians(pt1['lat'])
  lat2 = np.radians(pt2['lat'])
  lon1 = np.radians(pt1['lon'])
  lon2 = np.radians(pt2['lon'])
  dlon = lon2 - lon1
  dlat = lat2 - lat1
  altitude = (pt1['ele']+pt2['ele'])/2 if 'ele' in pt1 and 'ele' in pt2 else 0

  a = np.sin(dlat/2) * np.sin(dlat/2) + np.cos(lat1) * np.cos(lat2) \
      * np.sin(dlon/2) * np.sin(dlon/2)
  c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a));

  if not earthRadius:
    earthRadius = computeEarthRadius((pt1['lat']+pt2['lat']) / 2)
  d = (earthRadius + altitude) * c;

  return d

def computeEarthRadius(lat):
  '''
  return the earth radius at sea level for the given latitude
  see: https://rechneronline.de/earth-radius/
  '''
  lat = np.radians(lat)
  r =   ( (RADIUS_POLE**2*np.cos(lat))**2 + (RADIUS_EQUATOR**2*np.sin(lat))**2 )     \
      / ( (RADIUS_POLE*np.cos(lat))**2 + (RADIUS_EQUATOR*np.sin(lat))**2 )
  r = np.sqrt(r)
  return r

class GPX():
  '''
  GPX handler:
  - read GPX file
  - get elevation from open-elevation
  - compute hiking time
  -save GPX file

  '''
  def __init__(self, filename, dem, flatSpeed = FLAT_SPEED):

    self.flatSpeed = flatSpeed
    self.dem = dem

    self.initialTime = datetime.datetime.utcnow()
    self.tracks = []
    self.wayPoints = []

    self.nbTracks = self.read(filename)

  def read(self, filename):
    '''
    Read GPX file
    '''
    try:
      tree = ET.ElementTree(file=filename)
      root = tree.getroot()
    except:
      logger.error(f'unable to read gpx file "{filename}"')
      exit(-1)

    for i, child in enumerate(root):
      if 'wpt' in child.tag :
        # GPX waypoint tag
        pt=self.readDataElement(child)
        self.wayPoints.append(pt)
      elif 'trk' in child.tag or 'rte' in child.tag:
        # GPX trackpoint tag
        name = 'trk'+str(i)
        for data in child:
          if 'name' in data.tag :
            name = data.text
        self.tracks.append({'name':name, 'trackPoints':[]})
        for j, trackPt in enumerate(child.findall(".//*[@lat][@lon]")):
          pt=self.readDataElement(trackPt)
          if not pt['time']:
            time = 0
          self.tracks[-1]['trackPoints'].append(pt)

    return len(self.tracks)

  def write(self, outFile, trackNum = None):
    '''
    Write the data to a GPX file and store the running time of each point
    '''
    try:
      trackList = [self.tracks[trackNum]] if trackNum!=None else self.tracks
    except (IndexError, TypeError) as e:
      print(e)
      exit(-1)

    root = ET.Element('gpx', {'version':'1.0'})

    for wp in self.wayPoints:
      self.writeDataElement(root, 'wpt', wp)

    for trkList in trackList:
      trk = ET.SubElement(root, 'trk')
      e=ET.SubElement(trk, 'name')
      e.text = str(trkList['name'])
      trseg = ET.SubElement(trk, 'trkseg')
      for tp in trkList['trackPoints']:
        self.writeDataElement(trseg, 'trkpt', tp)

    try:
      tree = ET.ElementTree(root)
      tree.write(outFile, encoding='utf-8', xml_declaration=True)
    except:
      logger.error(f'unable to save  gpx file "{filename}"')

  def processTracks(self, trackNum = None):
    '''
    Get missing elevation values
    Compute cumulative distances (flat distance
    and  hicking times (using Tobler model)
    '''
    try:
      trackList = [self.tracks[trackNum]] if trackNum!=None else self.tracks
    except (IndexError, TypeError) as e:
      print(e)
      exit(-1)

    for i, trk in enumerate (trackList):
      self.dem.getElevation(trk['trackPoints'])
      tp0 = trk['trackPoints'][0]
      tp0['dist'] = 0
      tp0['time'] = 0
      tp0['ascent'] = 0
      tp0['descent'] = 0
      earthRadius = computeEarthRadius(tp0['lat'])
      # compute trackpoint time and other values
      for tp1 in trk['trackPoints'][1:]:
        d = computeDistance(tp0, tp1, earthRadius)
        tp1['dist'] = tp0['dist'] + d
        s = tp1['ele'] - tp0['ele']
        # treshold slop at 50.2°
        if abs(s) > 1.2 * d:
          logger.warning(f'computed slope ({s}) thresholded at 50.2')
          tp1['ele'] = tp0['ele']
          s = 0
        tp1['ascent'] = tp0['ascent']
        tp1['descent'] = tp0['descent']
        if s > 0:
          tp1['ascent'] += s
        else:
          tp1['descent'] += s
        h = computeHikingTime(d, s, self.flatSpeed)
        tp1['time'] = tp0['time'] + h
        tp0 = tp1
      # summup track values
      if not 'name' in trk:
        trk['name'] = f'track-{i+1}' if not trackNum else f'track-{tracknum+1}'
      trk['num'] = i+1
      trk['speed'] = self.flatSpeed
      trk['ascent'] = tp1['ascent']
      trk['descent'] = tp1['descent']
      trk['distance'] = tp1['dist'] / 1000 #km
      h = tp1['time'] - trk['trackPoints'][0]['time']
      trk['time'] = str(datetime.timedelta(hours=int(h), minutes=int((h % 1)*60)))
      trk['processed'] = True

  def getBoundingBox(self, trackNum = None):
    """
    compute the box encompassing the track waypoints
    return (top_left,bottom_right)
    """
    try:
      trackList = [self.tracks[trackNum]] if trackNum!=None else self.tracks
    except (IndexError, TypeError) as e:
      print(e)
      exit(-1)

    TL={'lat':-181, 'lon':361}
    BR={'lat': 181, 'lon':-361}
    for trk in trackList:
      tp = trk['trackPoints']
      maxLat = max(tp, key=lambda x:x['lat'])['lat']
      maxLon = max(tp, key=lambda x:x['lon'])['lon']
      minLat = min(tp, key=lambda x:x['lat'])['lat']
      minLon = min(tp, key=lambda x:x['lon'])['lon']
      TL['lat']=max(TL['lat'],maxLat)
      TL['lon']=min(TL['lon'],minLon)
      BR['lat']=min(BR['lat'],minLat)
      BR['lon']=max(BR['lon'],maxLon)
    return (TL,BR)

  def getProfile(self, trackNum, resolution = RESOLUTION):
    try:
      trk = self.tracks[trackNum]
    except (IndexError, TypeError) as e:
      print(e)
      exit(-1)

    colors = ['#4a5282','#171928','#111111', '#CCCCCC']
    border = 40
    distBar = 5000 # a bar every 5000m
    timeBar = 1 # a bar every 1h
    p = pathlib.Path(__file__).parent
    font = ImageFont.truetype(str(p.joinpath('fonts/FreeMonoBold.ttf')), 12)

    idx = resolution - 2 * border
    idy = int(resolution / 4) - 2 * border

    # compute scale and shift
    minEle = 10000
    maxEle = -10000
    l = []
    time = 0
    for j, tp in enumerate(trk['trackPoints']):
      minEle = min(minEle, tp['ele'])
      maxEle = max(maxEle, tp['ele'])
      if minEle == maxEle:
        minEle -= 10
        maxEle += 10
      l.append([tp['dist'],tp['ele']])
    shift = np.array([0, minEle])
    scale = np.array([(idx-1)/tp['dist'], - (idy-1)/(maxEle-minEle)])
    refShift = np.array([0,idy-1])

    # prepare curve and bar drawing
    imgCurve = Image.new('RGB', (idx,idy), color=colors[3])
    draw = ImageDraw.Draw(imgCurve)

    #draw curve
    nl = scale * (np.array(l) - shift) + refShift
    nl=np.concatenate((np.array([[0,idy-1]]),nl), axis = 0)
    nl=np.concatenate((nl,np.array([[idx-1,idy-1]])), axis = 0)
    draw.polygon([tuple(k) for k in nl], fill=colors[0])

    #draw bars
    dist = 0
    time = 0
    stepDist=[]
    stepTime=[]
    for tp in trk['trackPoints']:
      # distance bars
      d = int(tp['dist']/distBar)
      if d > dist:
        dist = d
        r = [[tp['dist'],tp['ele']],[tp['dist'],0]]
        nr = scale * (np.array(r) - shift) + refShift
        stepDist.append(nr[0,0])
        nr[0,0]-=1
        nr[1] = [nr[1,0]+1, idy-1]
        draw.rectangle([tuple(k) for k in nr], fill=colors[3])
      # hour bars
      t = int(tp['time']/timeBar)
      if t > time:
        time = t
        r = [[tp['dist'],tp['ele']],[tp['dist'],0]]
        nr = scale * (np.array(r) - shift) + refShift
        stepTime.append(nr[0,0])
        nr[0,0]-=1
        nr[1] = [nr[1,0]+1, 0]
        draw.rectangle([tuple(k) for k in nr], fill=colors[1])
    del draw

    # paste the curve image in a larger one containing the figure graduations
    imgFig = Image.new('RGB', (idx+2*border,idy+2*border), color=(255,255,255,255))
    imgFig.paste(imgCurve,(border, border))
    del imgCurve
    draw = ImageDraw.Draw(imgFig)

    # write text
    text = f'{maxEle:0.0f}m'
    draw.text((border-3,border), text, anchor='ra', font=font, fill=colors[2])
    draw.text((idx+border, border), text, anchor='la', font=font, fill=colors[2])
    text = f'{minEle:0.0f}m'
    draw.text((border-3,border+idy), text, anchor='rb', font=font, fill=colors[2])
    draw.text((idx+border,border+idy), text, anchor='lb', font=font, fill=colors[2])
    for i, p in enumerate(stepDist):
      draw.text((border+p, idy+border+3), f'{(i+1)*distBar/1000:0.0f}km', anchor='ma',
                font=font, fill=colors[2])
    for i, p in enumerate(stepTime):
      draw.text((border+p, border-3), f'{(i+1)*timeBar:0.0f}H', anchor='mb',
                font=font, fill=colors[2])
    del draw

    return imgFig

  def getTrackSummary(self, trackNum):
    try:
      trk = self.tracks[trackNum]
    except (IndexError, TypeError) as e:
      print(e)
      exit(-1)

    s = dict(trk)
    del s['trackPoints']
    return s

  def printSummary(self, trackNum):
    try:
      trk = self.tracks[trackNum]
    except (IndexError, TypeError) as e:
      print(e)
      exit(-1)

    print(f'\nTrack         : {trk["name"]}')
    print(f'Length        : {trk["distance"]:.2f}km')
    print(f'Total ascent  : {trk["ascent"]:+.0f}m')
    print(f'Total descent : {trk["descent"]:+.0f}m')
    print(f'Estimated time: {trk["time"]}\n')

  def readDataElement(self, xmlEl):
    '''
    Process GPX tags
    '''
    name = ''
    ele = time = 0
    lon=float(xmlEl.get('lon'))
    lat=float(xmlEl.get('lat'))
    for data in xmlEl:
      if 'name' in data.tag :
        # tag name
        name = data.text
      elif 'ele' in data.tag :
        # elevation
        ele = float(data.text)
      elif 'time' in data.tag :
        # running time if exist. Try several formatting.
        timeStr = data.text
        try:
          time = datetime.datetime.strptime(timeStr,'%Y-%m-%dT%H:%M:%S.%fZ')
        except:
          pass
        try:
          if not time:
            time = datetime.datetime.strptime(timeStr,'%Y-%m-%dT%H:%M:%SZ')
        except:
          pass
        try:
          if not time:
            time = datetime.datetime.strptime(timeStr,'%Y-%m-%d %H:%M:%S.%f')
        except:
          pass
        try:
          if not time:
            time = datetime.datetime.strptime(timeStr,'%Y-%m-%d %H:%M:%S')
        except:
          pass
        if time:
          time=time.hour+time.minute/60.
        else:
          logger.error('invalid date-time format (expected format : %Y-%m-%dT%H:%M:%S.%fZ)\n')
    pt={'lon':lon, 'lat':lat, 'name':name, 'ele':ele, 'time':time}
    return pt

  def writeDataElement(self, xmlEl, tag, data):
    '''
    Format GPX tags
    '''
    attrib = {'lat':f'{data["lat"]:.5f}','lon':f'{data["lon"]:.5f}'}
    ptEl=ET.SubElement(xmlEl, tag, attrib)
    if 'name' in data and data['name']:
      e = ET.SubElement(ptEl, 'name')
      e.text = str(data['name'])
    if 'ele' in data and data['ele']:
      e = ET.SubElement(ptEl, 'ele')
      e.text = f'{data["ele"]:.0f}'
    if 'time' in data and data['time']:
      e = ET.SubElement(ptEl, 'time')
      d = datetime.timedelta(hours=int(data['time']), minutes=int((data['time'] % 1)*60))
      t = self.initialTime + d
      # floor to millisencond -> [:-3]
      e.text = t.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]+'Z'
    if 'dist' in data:
      ET.SubElement(ptEl, 'extensions', {'km': f'{data["dist"]/1000.0:.3f}'})

    ptEl.tail = '\n'
