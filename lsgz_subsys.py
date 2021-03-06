#!/usr/bin/env python3

# Copyright  ©  2020-2021 IntelliProp Inc.
# Copyright (c) 2020 Hewlett Packard Enterprise Development LP
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import contextlib
import argparse
import os
import ctypes
import re
from uuid import UUID
from pathlib import Path
from importlib import import_module
from genz.genz_common import GCID
from pdb import set_trace, post_mortem
import traceback

def get_gcid(comp_path):
    gcid = comp_path / 'gcid'
    with gcid.open(mode='r') as f:
        return GCID(str=f.read().rstrip())

def get_cuuid(comp_path):
    cuuid = comp_path / 'c_uuid'
    with cuuid.open(mode='r') as f:
        return UUID(f.read().rstrip())

def get_cclass(comp_path):
    cclass = comp_path / 'cclass'
    with cclass.open(mode='r') as f:
        return int(f.read().rstrip())

def get_serial(comp_path):
    serial = comp_path / 'serial'
    with serial.open(mode='r') as f:
        return int(f.read().rstrip(), base=0)

comp_num_re = re.compile(r'.*/([^0-9]+)([0-9]+)')

def component_num(comp_path):
    match = comp_num_re.match(str(comp_path))
    return int(match.group(2))

from functools import wraps
from time import time

def timing(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        start = time()
        result = f(*args, **kwargs)
        end = time()
        print(' [{} elapsed time: {}] '.format(f.__name__, end-start), end='')
        return result
    return wrapper

@timing
def get_struct(fpath, map, parent=None, core=None, verbosity=0):
    fname = fpath.name
    with fpath.open(mode='rb') as f:
        try:  # Revisit: workaround for zero-length files
            data = bytearray(f.read())
        except OSError:
            size = fpath.stat().st_size
            if size == 0:
                return None
            else:
                raise
        # special case for 'interface' - optional fields
        if (fname == 'interface' and
            len(data) >= ctypes.sizeof(genz.InterfaceXStructure)):
            fname = 'interfaceX'
        struct = map.fileToStruct(fname, data, path=fpath,
                                  parent=parent, core=core,
                                  verbosity=verbosity)
        return struct

def get_parent(fpath, dpath, parents):
    parent = parents['core@0x0']  # default parent, if we do not find another
    for p in reversed(dpath.parents[0].parts):
        if p == 'control' or p == 'dr':
            break
        if '@0x' in p:
            parent = parents[p]
            break
    return parent

def ls_comp(ctl, map, ignore_dr=True):
    parents = {}
    drs = []
    # do core structure first
    core_path = ctl / 'core@0x0' / 'core'
    core = get_struct(core_path, map, verbosity=args.verbosity)
    print('  {}='.format('core@0x0'), end='')
    print(core)
    parents['core@0x0'] = core
    for dir, dirnames, filenames in os.walk(ctl):
        #print('{}, {}, {}'.format(dir, dirnames, filenames))
        if dir[-3:] == '/dr':
            drs.append(Path(dir))
            continue
        elif ignore_dr and dir.find('/dr/') >= 0:
            continue
        dpath = Path(dir)
        for file in filenames:
            if file == 'core':  # we already did core
                continue
            print('  {}='.format(dpath.name), end='')
            fpath = dpath / file
            parent = get_parent(fpath, dpath, parents)
            struct = get_struct(fpath, map, core=core, parent=parent,
                                verbosity=args.verbosity)
            print(struct)
            parents[dpath.name] = struct
        # end for filenames
    # end for dir
    return drs

def main():
    global args
    global cols
    global genz
    parser = argparse.ArgumentParser()
    #parser.add_argument('file', help='the file containing control space')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('-G', '--genz-version', choices=['1.1'],
                        default='1.1',
                        help='Gen-Z spec version of Control Space structures')
    parser.add_argument('-P', '--post_mortem', action='store_true',
                        help='enter debugger on uncaught exception')
    parser.add_argument('-S', '--struct', action='store',
                        help='input file representing a single control structure')
    args = parser.parse_args()
    if args.verbosity > 5:
        print('Gen-Z version = {}'.format(args.genz_version))
    genz = import_module('genz.genz_{}'.format(args.genz_version.replace('.', '_')))
    map = genz.ControlStructureMap()
    if args.struct:
        fpath = Path(args.struct)
        struct = get_struct(fpath, map, verbosity=args.verbosity)
        print(struct)
        return
    sys_devices = Path('/sys/devices')
    dev_fabrics = sys_devices.glob('genz*')
    for fab in dev_fabrics:
        fabnum = component_num(fab)
        #print('fabric: {}, num={}'.format(fab, fabnum))
        bridges = fab.glob('bridge*')
        for br in bridges:
            gcid = get_gcid(br)
            cuuid = get_cuuid(br)
            cclass = get_cclass(br)
            serial = get_serial(br)
            brnum = component_num(br)
            print('{}:{} {:9s} {}:{:#018x}'.format(fabnum, gcid,
                                                   'bridge{}'.format(brnum),
                                                   cuuid, serial))
            if args.verbosity < 1:
                continue
            ctl = br / 'control'
            drs = ls_comp(ctl, map)
            for dr in drs:
                print('dr: {}'.format(dr))  # Revisit: better format
                if args.verbosity < 1:
                    continue
                # Revist: handle nested drs?
                _ = ls_comp(dr, map, ignore_dr=False)
        # end for br
    # end for fab
    genz_fabrics = Path('/sys/bus/genz/fabrics')
    fab_comps = genz_fabrics.glob('fabric*/*:*/*:*:*')
    for comp in fab_comps:
        cuuid = get_cuuid(comp)
        cclass = get_cclass(comp)
        serial = get_serial(comp)
        print('{} {:9s} {}:{:#018x}'.format(comp.name, genz.cclass_name[cclass],
                                            cuuid, serial))
        if args.verbosity < 1:
            continue
        ctl = comp / 'control'
        drs = ls_comp(ctl, map)
        for dr in drs:
            print('dr: {}'.format(dr))  # Revisit: better format
            if args.verbosity < 1:
                continue
            # Revist: handle nested drs?
            _ = ls_comp(dr, map, ignore_dr=False)
        # end for dr
    # end for comp

if __name__ == '__main__':
    try:
        main()
    except Exception as post_err:
        if args.post_mortem:
            traceback.print_exc()
            post_mortem()
        else:
            raise
