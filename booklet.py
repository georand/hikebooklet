# -*- coding: utf-8 -*-
"""
 HikeBooklet
 author: georand
 source: https://github.com/georand/hikebooklet
 date: 2021
"""

import argparse, pathlib, logging
from gpxmap import GPXMap

from config import *

logger=logging.getLogger(__name__)

htmlStart = '<!DOCTYPE html> <style type="text/css"> @media print { footer {page-break-after: always;} </style> <html> <body>\n'

htmlTrack = '<center> <h2>{name}</h2><p><img style="border:5px solid"; src="{mapPath}"></p><p> <img img style="border:5px solid"; src="{profilePath}"></p> <h4><table width={width}><tr><td align="center">Length: {distance:.2f}km</td><td align="center">Total Ascent: {ascent:+.0f}m</td><td align="center">Total descent: {descent:+.0f}m</td><td align="center">Estimated duration: {time} &nbsp&nbsp(at {speed}km/h flat speed) </td></tr></table></h4> <footer><br><br><table width={width}><tr><td align="left"><a href="https://github.com/georand/hikebooklet">https://github.com/georand/hikebooklet</a></td><td align="right">{num}</td></tr></table> </footer></center>'

htmlEnd = '</body></html>'

class Booklet():

  def __init__(self, gpx, cache, resolution = RESOLUTION):
    self.resolution = resolution
    self.cache = cache
    self.gpx = gpx

  def write(self, dirPath):

    try:
      dirPath.mkdir(exist_ok = True)
    except FileNotFoundError as e:
      logger.error(f'unable to create directory {str(dirPath)}')
      exit(-1)

    html = htmlStart
    for i in range (0, self.gpx.nbTracks):
      logger.info(f'processing track {i+1}/{self.gpx.nbTracks}')
      self.gpx.processTracks(i)
      data = self.gpx.getTrackSummary(i)
      data['profilePath'] = f'profile-{i+1:02d}.png'
      data['mapPath'] = f'map{i+1:02d}.png'
      data['width'] = self.resolution
      profile = self.gpx.getProfile(i, resolution = self.resolution)
      profile.save(str(dirPath.joinpath(data['profilePath'])), 'png')
      logger.info(f'mapping track {i+1}/{self.gpx.nbTracks}')
      mapImg = GPXMap(self.gpx, trackNum=i,
                      resolution = self.resolution, cache = self.cache)
      mapImg.mapImg.save(str(dirPath.joinpath(data['mapPath'])),'png')
      html+= htmlTrack.format(**data)
      if logger.level <= logging.INFO:
        self.gpx.printSummary(i)
    html += htmlEnd

    try:
      path = dirPath.joinpath('index.html')
      with open(path,'w') as f:
        f.write(html)
    except:
      logger.error('unable to save booklet in file {str(path)}')

    self.gpx.write(dirPath.joinpath('rsl.gpx'))

    logger.info(f'booklet available here: {dirPath.joinpath("index.html")}')
