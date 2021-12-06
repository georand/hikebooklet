# -*- coding: utf-8 -*-
"""
 HikeBooklet
 author: georand
 source: https://github.com/georand/hikebooklet
 date: 2021
"""

import pathlib, base64, logging

from config import *

logger=logging.getLogger(__name__)

class CacheDir():
  def __init__(self, path = CACHE_PATH, maxSize = CACHE_MAX_SIZE, keep = CACHE_KEEP):
    '''
    a basic disk cache directory management

    path: cache path
    maxSize: cache max size in MB
    keep: list of filenames to be kept permanently
    '''
    self.maxSize = maxSize*1024*1024
    self.path = pathlib.Path(path).expanduser()
    self.keep = keep
    if not self.path.exists():
      self.path.mkdir()

  def check(self, filename):
    p = self.path.joinpath(filename)
    if p.exists():
      p.touch()
      return p
    else:
      return None

  def loadData(self, filename, crypt = False):
    path = self.path.joinpath(filename)
    data = None
    if path.exists():
      path.touch()
      with open(path,'rb') as f:
        data = f.read()
        if crypt:
          data = base64.b64decode(data)
        logger.debug(f'retrieving file "{filename}" from cache')
    return data

  def saveData(self, filename, data, crypt = False):
    if crypt:
      data = base64.b64encode(data)
    path = self.path.joinpath(filename)
    with open(path,'wb') as f:
      f.write(data)
      logger.debug(f'storing file "{filename}" in cache')
    self.clean()
    return path

  def clean(self):
    dirSize = sum(f.stat().st_size for f in self.path.glob('**/*') if f.is_file())
    files = sorted([*self.path.iterdir()], key=lambda p: p.stat().st_mtime, reverse = True)
    while len(files) > 2  and dirSize > self.maxSize:
      f = files.pop()
      if not str(f.name) in self.keep:
        dirSize -= f.stat().st_size
        f.unlink()
        logger.debug(f'removing  file "{filename}" from cache')
