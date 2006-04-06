#! /bin/sh
rsync -r -R -L -v -l -C -p --exclude=*.py --exclude=*.sh --exclude=digikam.xml --exclude=Thumbs.db --exclude=thumbs.db --exclude=*.in --rsh=ssh ./* mcfletch@shell.sourceforge.net:~/starpy/doc/
ssh mcfletch@shell.sourceforge.net "/usr/local/bin/sfgrp starpy < ~/mvstarpysite.sh"
