#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
 HikeBooklet
 author: georand
 source: https://github.com/georand/hikebooklet
 date: 2021
"""

import sys, argparse, pathlib, logging

from config import *
from cache import CacheDir as Cache
from dem import DEM
from gpx import GPX
from booklet import Booklet

if __name__ == "__main__":

  parser = argparse.ArgumentParser(description=
    'Create a hiking booklet from a GPX file using maps from Openstopomap\nand DEM (Digital elevation Model) from USGS\n !!! prior-registration at https://urs.earthdata.nasa.gov/profile is required in order to get DEM data !!!')
  parser.add_argument('-v', action='count', required=False,
                      dest='verbose', default=0,
                      help='print information messages to stderr')
  parser.add_argument('-s', type=float, metavar='speed', required=False,
                      dest='flatSpeed', default=FLAT_SPEED,
                      help='flat speed (default to 4,5km/h)')
  parser.add_argument('-a', metavar='username:password', required=False,
                      dest='auth', default='',
                      help='authentication information for the DEM server')
  parser.add_argument('-i', type=pathlib.Path, metavar='input_gpx_file', required=True,
                      dest='GPXFile', default=None,
                      help='input gpx file')
  parser.add_argument('outputDir', nargs=1, type=pathlib.Path, metavar='output_dir',
                      help='directory path where resulting data will be stored')
  args = parser.parse_args()

  logLevel = max(10, 30 - args.verbose * 10) # ERROR:40, WARNING:30 INFO:20 DEBUG:10

  logging.basicConfig(level=logLevel, format='%(name)s - %(levelname)s - %(message)s',
                      stream=sys.stderr)

  cache = Cache(CACHE_PATH, CACHE_MAX_SIZE)

  auth = args.auth.split(':') if ':' in args.auth else [None,None]

  dem = DEM(username = auth[0], password = auth[1], cache = cache)

  gpx = GPX(args.GPXFile, dem = dem, flatSpeed = args.flatSpeed)

  booklet = Booklet(resolution = RESOLUTION, gpx = gpx, cache = cache)

  booklet.write(args.outputDir[0])
