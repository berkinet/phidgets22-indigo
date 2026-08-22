#!/usr/bin/env python3

#
# Use comments from the Phidget22 python library to generate a JSON file mapping
# constants to human-readable descriptions.
#

import argparse
import os
import re
import json
import glob

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phidgetpath', help="Path to Phdiget22 python library",
        default="Phidgets22.indigoPlugin/Contents/Server Plugin/Phidget22/")
    parser.add_argument('--output', help="JSON output file",
        default="Phidgets22.indigoPlugin/Contents/Resources/phidgets.json")
    args = parser.parse_args()

    output = {}

    for phidget_source in glob.iglob("%s/*.py" % args.phidgetpath):
        phidget_class = os.path.basename(phidget_source).split('.')[0]
        with open(os.path.join(phidget_source), 'rb') as f:
            for m in re.finditer(r'^\t# (?P<desc>.+)\n^\t(?P<def>[0-9A-Z_]+) = (?P<value>[\d]+)',
                                 f.read().decode("UTF-8"), re.MULTILINE):
                if phidget_class not in output:
                    output[phidget_class] = []
                output[phidget_class].append({
                    'value' : int(m.group('value')),
                    'description' : m.group('desc'),
                    'enum' : m.group('def')
                    })
    
    with open(args.output, 'w', encoding='utf8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4, sort_keys=True)

if __name__ == "__main__":
    main()
