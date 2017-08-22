#!/bin/sh
set -e

if [ $# -ne 5 ] ; then
    echo "Usage: svg2png.sh image.svg image.png width height colors"
    exit 1
fi

inkscape $1 --export-width=$3  --export-height=$4 --export-png=tmp.png
pngnq -s 1 -f -n $5 tmp.png
zopflipng -m tmp-nq8.png $2
rm tmp.png tmp-nq8.png
