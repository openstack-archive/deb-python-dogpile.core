import os
import sys
import re

from setuptools import setup, find_packages

v = open(os.path.join(os.path.dirname(__file__), 'dogpile', 'core', '__init__.py'))
VERSION = re.compile(r".*__version__ = '(.*?)'", re.S).match(v.read()).group(1)
v.close()

readme = os.path.join(os.path.dirname(__file__), 'README.rst')

setup(name='dogpile.core',
      version=VERSION,
      description="A 'dogpile' lock, typically used as a component of a larger caching solution",
      long_description=open(readme).read(),
      classifiers=[
      'Development Status :: 4 - Beta',
      'Intended Audience :: Developers',
      'License :: OSI Approved :: BSD License',
      'Programming Language :: Python',
      'Programming Language :: Python :: 3',
      ],
      keywords='caching',
      author='Mike Bayer',
      author_email='mike_mp@zzzcomputing.com',
      url='http://bitbucket.org/zzzeek/dogpile.core',
      license='BSD',
      packages=find_packages('.', exclude=['ez_setup', 'tests*']),
      namespace_packages=['dogpile'],
      zip_safe=False,
      install_requires=[],
      test_suite='nose.collector',
      tests_require=['nose'],
)
