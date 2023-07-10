from setuptools import setup, find_packages

setup(
    name='utils',
    version='1.0.1',
    packages=find_packages(),
    install_requires=[
        "requests==2.25.1",
        # "elasticsearch",
        "elasticsearch2==2.5.1",
        "python-dateutil==2.8.1"
    ],
    url='http://jisc.ac.uk/',
    author='Ruben Romartinez',
    author_email='ruben.alonso@jisc.ac.uk',
    description='Utils packege for connecting to DB and WS as well as logs and exception handler',
    license='Copyheart',
    classifiers=[
        'Development Status :: 1 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: Copyheart',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
