from setuptools import setup, find_packages

setup(
    name = 'engine',
    version = '1.0.1',
    packages = find_packages(),
    install_requires = [
        "utils"
    ],
    url = 'http://jisc.ac.uk/',
    author = 'Mateusz Kasiuba',
    author_email = 'mateusz.kasiuba@jisc.ac.uk',
    description = 'Package to provide different engines for different WS providers',
    license = 'Copyheart',
    classifiers = [
        'Development Status :: 1 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: Copyheart',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
