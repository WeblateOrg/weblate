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

Does Weblate support other VCS than Git?
----------------------------------------

Not currently. Weblate requires distributed VCS and could be probably adjusted
to work with anything else than Git, but somebody has to implement this support.
