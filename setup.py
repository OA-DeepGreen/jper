from setuptools import setup, find_packages

setup(
    name='jper',
    version='1.1',
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "beautifulsoup4~=4.12",
        "openpyxl~=3.1",
        "Werkzeug<3.0",  # FIXME: we have passwords using sha1 that are undecodable after 3.0,
        "chardet~=5.2",
        "Flask<3.0",   # FIXME: after 3, needs version 3 of werkzeug,
        "Flask-Login~=0.6",
        "itsdangerous~=2.2",
        "requests~=2.32",
        "simplejson~=3.19",
        "lxml~=5.3",
        "Flask-WTF~=1.2",
        "nose~=1.3",
        "Flask-Mail~=0.10",
        "Flask-Babel~=4.0",
        "python-dateutil~=2.9",
        "unidecode~=1.3",
        "schedule~=1.2",
        "jsonpath-rw-ext~=1.2",
        "unicodecsv~=0.14",
        "Jinja2~=3.1",
        "esprit",
        "octopus",
        "paramiko"
    ],
    url='http://cottagelabs.com/',
    author='Cottage Labs',
    author_email='us@cottagelabs.com',
    description='Jisc Publications Event Router',
    classifiers=[
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
