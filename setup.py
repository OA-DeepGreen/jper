from setuptools import setup, find_packages

setup(
    name = 'jper',
    version = '1.0.0-p3',
    packages = find_packages(),
    install_requires = [
        "beautifulsoup4==4.9.3"
        "wtforms==2.3.3"
        "werkzeug==1.0.1",
        "Flask==1.1.2",
        "Flask-Login==0.5.0",
        "requests==2.25.1",
        "simplejson==3.17.2",
        "lxml==4.6.2",
        "Flask-WTF==0.14.3",
        "nose==1.3.7",
        "Flask-Mail==0.9.1",
        "Flask-Babel==2.0.0",
        "python-dateutil==2.8.1",
        "unidecode==1.2.0",
        "schedule==1.0.0",
        "jsonpath-rw-ext==1.2.2",
        "unicodecsv==0.14.1",
        "esprit",
        "octopus"
    ],
    url = 'http://cottagelabs.com/',
    author = 'Cottage Labs',
    author_email = 'us@cottagelabs.com',
    description = 'Jisc Publications Event Router',
    classifiers = [
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
