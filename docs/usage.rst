Usage
=====

Installation
------------

To use climepi, download the source code from the github repository
(https://github.com/will-s-hart/climate-epidemics). The package and its dependencies can
then be installed via conda into a new virtual environment using the provided
environment.yml file: working in the repository root directory, run

.. code-block:: console

    climate-epidemics $ conda env create -f environment.yml

.. note::
    1. On an Apple silicon Mac, it is currently necessary to run ``CONDA_SUBDIR=osx-64
    conda env create -f environment.yml``, since not all dependencies have arm64 or
    universal builds available on conda-forge.
    2. Using mamba instead of conda may substantially speed up the installation process.

The virtual environment can be activated using the following
command:   

.. code-block:: console
    
    climate-epidemics $ conda activate climepi

Front-end application
---------------------

This package provides a browser-based front-end application that can be used to run and
visualize the output of climate-sensitive epidemiological models.

If the climepi package is installed within the current python virtual environment, the
application can be initiated from the command line by running

.. code-block:: console

    (climepi) climate-epidemics $ python -m climepi.app

The application is built using the `Panel` library.