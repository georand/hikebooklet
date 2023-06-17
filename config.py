# -*- coding: utf-8 -*-
"""
 HikeBooklet
 author: georand
 source: https://github.com/georand/hikebooklet
 date: 2021
"""

# Hicking speed
FLAT_SPEED = float(4.5) # standard value: 4.5 to 5  km/h

# resolution in pixel for the map and profile images
RESOLUTION = 1024

# track and point colors
COLORS = ['#236AB9','#FC7307']

# url for map requests
URL_MAP=r'https://tile.opentopomap.org/{}/{}/{}.png'
# idem for openstreetmap
#URL_MAP=r'https://tile.openstreetmap.org/{}/{}/{}.png'

# url for Digital Elvation Model download (see below for credentials)
URL_DEM = r'https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/{}'
URL_DEM_AUTH = 'urs.earthdata.nasa.gov'

# tile name format for DEM files
DEM_TILE_NAME = r'{}.SRTMGL1.hgt.zip'

DEM_RESOLUTION = 3601 # 3601x3601 for STRM1 and 1201x101 SRTM3

# cache directory for the map tiles
CACHE_PATH = '~/.cache/hikebooklet'

# cache size in MB
CACHE_MAX_SIZE = 128

# list of file to be kept permanently in cache
CACHE_KEEP = ['usgs.dat']
