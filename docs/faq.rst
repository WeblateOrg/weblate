Frequently Asked Questions
==========================

Requests sometimes fail with too many open files error
------------------------------------------------------

This happens sometimes when your Git repository grows too much and you have
more of them. Compressing the Git repositories will improve this situation.

The easiest way to do this is to run:

.. code-block:: sh

    cd repos
    for d in */* ; do
        pushd $d
        git gc
        popd
    done

Fulltext search is too slow
---------------------------

Depending on various conditions (frequency of updates, server restarts and
other), fulltext index might get too fragmented over time. It is recommended to
rebuild it from scratch time to time:

.. code-block:: sh

    ./manage.py rebuild_index --clean

I get "Lock Error" quite often while translating
------------------------------------------------

This is usually caused by concurent updates to fulltext index. In case you are
running multithreaded server (eg. mod_wsgi), this happens quite often. For such
setup it is recommended to enable :setting:`OFFLOAD_INDEXING`.

Rebuilding index has failed with "No space left on device"
----------------------------------------------------------

Whoosh uses temporary directory to build indices. In case you have small /tmp
(eg. using ramdisk), this might fail. Change used temporary directory by passing 
as ``TEMP`` variable:

.. code-block:: sh

    TEMP=/path/to/big/temp ./manage.py rebuild_index --clean

Does Weblate support other VCS than Git?
----------------------------------------

Not currently. Weblate requires distributed VCS and could be probably adjusted
to work with anything else than Git, but somebody has to implement this support.

Why does Weblate force to have show all po files in single tree?
----------------------------------------------------------------

Weblate was designed in a way that every po file is represented as single
subproject. This is beneficial for translators, that they know what they are
actually translating. If you feel your project should be translated as one,
consider merging these po files. It will make life easier even for translators
not using Weblate.

.. note::

    In case there will be big demand for this feature, it might be implemented
    in future versions, but it's definitely not a priority for now.
