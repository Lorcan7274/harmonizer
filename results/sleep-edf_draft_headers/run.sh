#!/bin/sh
# one CANONICAL run per layout, because the group is chosen per run
cd "$(dirname "$0")" || exit 1
luna lists/L01.lst -o L01.db -s 'CANONICAL file=rules.sigs group=L01 drop-originals'
luna lists/L02.lst -o L02.db -s 'CANONICAL file=rules.sigs group=L02 drop-originals'
