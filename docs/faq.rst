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
