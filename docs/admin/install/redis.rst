Installing Redis (Caching backend)
================


Installing Redis via apt
------------------------

.. code-block:: sh

    apt install redis-server -y

Installing Redis manually
-------------------------

.. code-block:: sh

    # Downloading the archiv
    wget https://github.com/redis/redis/archive/7.0.2.tar.gz -O Redis.tar.gz

    # Unpack the archiv
    gunzip Redis.tar.gz && tar xvf Redis.tar

    # Rename the directory
    mv redis-* redis

    # Enter the directory
    cd redis

    # Remove unimportant (optional, actually irrelevant)
    rm -r .g* 00-RELEASENOTES BUGS CONDUCT CONTRIBUTING COPYING INSTALL MANIFESTO

    # Compiling redis
    make

    # Test the installation (optional)
    make test

    # Run redis
    screen -S Redis src/redis-server

    # Leave directory

    cd ..