from setuptools import setup

setup(name='PyAMA',
      version='0.1.8',
      description='Desktop application for extracting single-cell fluorescence from single-cell time-lapse microscopy movies',
      url='https://github.com/SoftmatterLMU-RaedlerGroup/pyama',
      author='Daniel Woschée',
      author_email='daniel.woschee@physik.lmu.de',
      license='MIT',
      package_dir={"": "src"},
      packages=setuptools.find_packages(where="src"),
      classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        ],
      python_requires=">=3.8"
      )