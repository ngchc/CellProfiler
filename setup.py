import distutils
import glob
import os
import shlex
import setuptools
import setuptools.command.build_ext
import setuptools.command.install
import setuptools.dist
import sys

try:
    import matplotlib
    import numpy # for proper discovery of its libraries by distutils
    import scipy.sparse.csgraph._validation
    import zmq   # for proper discovery of its libraries by distutils
    import zmq.libzmq
except ImportError:
    pass

from cellprofiler.utilities.version import version_string

with open("cellprofiler/frozen_version.py", "w") as fd:
    fd.write("version_string='%s'\n" % version_string)

if sys.platform.startswith("win"):
    import _winreg
    try:
        import py2exe
        has_py2exe = True
    except:
        has_py2exe = False
else:
    has_py2exe = False    

# Recipe needed to get real distutils if virtualenv.
# Error message is "ImportError: cannot import name dist"
# when running app.
# See http://sourceforge.net/p/py2exe/mailman/attachment/47C45804.9030206@free.fr/1/
#
if hasattr(sys, 'real_prefix'):
    # Running from a virtualenv
    assert hasattr(distutils, 'distutils_path'), \
           "Can't get real distutils path"
    libdir = os.path.dirname(distutils.distutils_path)
    sys.path.insert(0, libdir)
    #
    # Get the system "site" package, not the virtualenv one. This prevents
    # site.virtual_install_main_packages from being called, resulting in
    # "IOError: [Errno 2] No such file or directory: 'orig-prefix.txt'
    #
    del sys.modules["site"]
    import site
    assert not hasattr(site, "virtual_install_main_packages")

#
# Recipe for ZMQ
#
if sys.platform.startswith("win"):
    #
    # See http://www.py2exe.org/index.cgi/Py2exeAndzmq
    # Recipe needed for py2exe to package libzmq.dll
    os.environ["PATH"] += os.path.pathsep + os.path.split(zmq.__file__)[0]

zmq_includes = ["zmq", "zmq.utils", "zmq.utils.*", "zmq.utils.strtypes"]

zmq_version = tuple([int(_) for _ in zmq.__version__.split(".")])
if zmq_version >= (14, 0, 0):
    # Backends are new in 14.x
    zmq_includes += [
        "zmq.backend", "zmq.backend.cython", "zmq.backend.cython.*",
        "zmq.backend.cffi", "zmq.backend.cffi.*"]
    
class Install(setuptools.command.install.install):
    def run(self):
        try:
            import clint.textui
            import requests
        except ImportError:
            raise ImportError

        version = "1.0.3"

        directory = os.path.join(self.build_lib, "imagej", "jars")

        if not os.path.exists(directory):
            os.makedirs(directory)

        prokaryote = "{}/prokaryote-{}.jar".format(os.path.abspath(directory), version)

        resource = "https://github.com/CellProfiler/prokaryote/" + "releases/download/{tag}/prokaryote-{tag}.jar".format(tag=version)

        request = requests.get(resource, stream=True)

        if not os.path.isfile(prokaryote):
            with open(prokaryote, "wb") as f:
                total_length = int(request.headers.get("content-length"))

                chunks = clint.textui.progress.bar(request.iter_content(chunk_size=32768), expected_size=(total_length / 32768) + 1, hide=not self.verbose)

                for chunk in chunks:
                    if chunk:
                        f.write(chunk)

                        f.flush()

        dependencies = os.path.abspath(os.path.join(
            self.build_lib, 'imagej', 'jars', 
            'cellprofiler-java-dependencies-classpath.txt'))

        if not os.path.isfile(dependencies):
            dependency = open(dependencies, "w")

            dependency.write(prokaryote)

            dependency.close()

        setuptools.command.install.install.run(self)


class Test(setuptools.Command):
    user_options = [
        ("pytest-args=", "a", "arguments to pass to py.test")
    ]

    def initialize_options(self):
        self.pytest_args = []

    def finalize_options(self):
        pass

    def run(self):
        try:
            import pytest
            import unittest
        except ImportError:
            raise ImportError

        import cellprofiler.__main__
        import cellprofiler.utilities.cpjvm

        #
        # Monkey-patch pytest.Function
        # See https://github.com/pytest-dev/pytest/issues/1169
        #
        try:
            from _pytest.unittest import TestCaseFunction

            def runtest(self):
                setattr(self._testcase, "__name__", self.name)
                self._testcase(result=self)

            TestCaseFunction.runtest = runtest
        except:
            pass

        try:
            import ilastik.core.jobMachine

            ilastik.core.jobMachine.GLOBAL_WM.set_thread_count(1)
        except ImportError:
            pass

        cellprofiler.utilities.cpjvm.cp_start_vm()

        errno = pytest.main(self.pytest_args)

        cellprofiler.__main__.stop_cellprofiler()

        sys.exit(errno)

if has_py2exe:        
    class CPPy2Exe(py2exe.build_exe.py2exe):
        user_options = py2exe.build_exe.py2exe.user_options + [
            ("msvcrt-redist=", None, 
             "Directory containing the MSVC redistributables")]
        def initialize_options(self):
            py2exe.build_exe.py2exe.initialize_options(self)
            self.msvcrt_redist = None
            
        def finalize_options(self):
            py2exe.build_exe.py2exe.finalize_options(self)
            if self.msvcrt_redist is None:
                try:
                    key = _winreg.OpenKey(
                        _winreg.HKEY_LOCAL_MACHINE,
                        r"SOFTWARE\Wow6432Node\Microsoft\VisualStudio\9.0"+
                        r"\Setup\VC")
                    product_dir = _winreg.QueryValueEx(key, "ProductDir")[0]
                    self.msvcrt_redist = os.path.join(
                        product_dir, "redist", "amd64", "Microsoft.VC90.CRT")
                except WindowsError:
                    self.announce(
                        "Package will not include MSVCRT redistributables", 3)
            
        def run(self):
            #
            # py2exe runs install_data a second time. We want to inject some
            # data files into the dist but we do it here so that if the user
            # does a straight "install", they won't end up dumped into their
            # Python directory.
            #
            import javabridge
            from cellprofiler.utilities.cpjvm import get_path_to_jars
            
            if self.distribution.data_files is None:
                self.distribution.data_files = []
            self.distribution.data_files += matplotlib.get_py2exe_datafiles()
            self.distribution.data_files.append(
                ("javabridge/jars", javabridge.JARS))
            self.distribution.data_files.append(
                ("imagej/jars", 
                 glob.glob(os.path.join(get_path_to_jars(), "prokaryote*.jar")) +
                 [os.path.join(get_path_to_jars(), 
                               "cellprofiler-java-dependencies-classpath.txt")]))
            self.distribution.data_files.append(
                ("artwork", glob.glob("artwork/*")))
            #
            # Add ilastik UI files
            #
            if has_ilastik:
                ilastik_root = os.path.dirname(ilastik.__file__)
                for root, directories, filenames in os.walk(ilastik_root):
                    relpath = root[len(os.path.dirname(ilastik_root))+1:]
                    ui_filenames = [
                        os.path.join(root, f) for f in filenames
                        if any([f.lower().endswith(ext) 
                                for ext in ".ui", ".png"])]
                    if len(ui_filenames) > 0:
                        self.distribution.data_files.append(
                            (relpath, ui_filenames))
                    
            #
            # Must include libzmq.pyd without renaming because it's
            # linked against.
            #
            if zmq_version >= (14, 0, 0):
                self.distribution.data_files.append(
                    (".", [zmq.libzmq.__file__]))
            #
            # Same with vigranumpycore.pyd
            #
            try:
                import vigra.vigranumpycore
                self.distribution.data_files.append(
                    (".", [vigra.vigranumpycore.__file__]))
            except ImportError:
                pass
            
            if self.msvcrt_redist is not None:
                sources = [
                    os.path.join(self.msvcrt_redist, filename)
                    for filename in os.listdir(self.msvcrt_redist)]
                self.distribution.data_files.append(
                    ("./Microsoft.VC90.CRT", sources))

            py2exe.build_exe.py2exe.run(self)
        
    class CellProfilerMSI(distutils.core.Command):
        description = \
            "Make CellProfiler.msi using the CellProfiler.iss InnoSetup compiler"
        user_options = [("without-ilastik", None, 
                         "Do not include a start menu entry for Ilastik"),
                        ("output-dir=", None,
                         "Output directory for MSI file"),
                        ("msi-name=", None,
                         "Name of MSI file to generate (w/o extension)")]
        
        def initialize_options(self):
            self.without_ilastik = None
            self.py2exe_dist_dir = None
            self.output_dir = None
            self.msi_name = None
        
        def finalize_options(self):
            self.set_undefined_options(
                "py2exe", ("dist_dir", "py2exe_dist_dir"))
            if self.output_dir is None:
                self.output_dir = "output"
            if self.msi_name is None:
                self.msi_name = \
                    "CellProfiler-" + self.distribution.metadata.version
        
        def run(self):
            if not os.path.isdir(self.output_dir):
                os.makedirs(self.output_dir)
            with open("version.iss", "w") as fd:
                fd.write("""
    AppVerName=CellProfiler %s
    OutputBaseFilename=%s
    """ % (self.distribution.metadata.version, 
           self.msi_name))
            with open("ilastik.iss", "w") as fd:
                if not self.without_ilastik:
                    fd.write(
                        'Name: "{group}\Ilastik"; '
                        'Filename: "{app}\CellProfiler.exe"; '
                        'Parameters:"--ilastik"; WorkingDir: "{app}"\n')
            if numpy.log(sys.maxsize) / numpy.log(2) > 32:
                cell_profiler_iss = "CellProfiler64.iss"
            else:
                cell_profiler_iss = "CellProfiler.iss"
            required_files = [
                os.path.join(self.py2exe_dist_dir, "CellProfiler.exe"), 
                cell_profiler_iss]
            compile_command = self.__compile_command()
            compile_command = compile_command.replace("%1", cell_profiler_iss)
            compile_command = shlex.split(compile_command)
            self.make_file(
                required_files, 
                os.path.join(self.output_dir, self.msi_name + ".msi"), 
                self.spawn, [compile_command],
                "Compiling %s" % cell_profiler_iss)
            os.remove("version.iss")
            os.remove("ilastik.iss")

        def __compile_command(self):
            """Return the command to use to compile an .iss file
            """
            try:
                key = _winreg.OpenKey(
                    _winreg.HKEY_CLASSES_ROOT, 
                    "InnoSetupScriptFile\\shell\\Compile\\command")
                result = _winreg.QueryValueEx(key,None)[0]
                key.Close()
                return result
            except WindowsError:
                if key:
                    key.Close()
                raise distutils.errors.DistutilsFileError, "Inno Setup does not seem to be installed properly. Specifically, there is no entry in the HKEY_CLASSES_ROOT for InnoSetupScriptFile\\shell\\Compile\\command"
            
        
packages = setuptools.find_packages(exclude=[
        "*.tests",
        "*.tests.*",
        "tests.*",
        "tests",
        "tutorial"
    ])

#
# These includes are for packaging Ilastik as an application along with
# CellProfiler for py2exe and py2app (but not for install).
#
ilastik_includes = []
try:
    import ilastik
    ilastik_includes = [ 
        "ilastik", "ilastik.*", "ilastik.core.*", "ilastik.core.overlays.*", 
        "ilastik.core.unsupervised.*", "ilastik.gui.*", 
        "ilastik.gui.overlayDialogs.*", "ilastik.gui.ribbons.*",
        "ilastik.modules.classification.*", 
        "ilastik.modules.classification.core.*",
        "ilastik.modules.classification.core.classifiers.*",
        "ilastik.modules.classification.core.features.*",
        "ilastik.modules.classification.gui.*",
        "ilastik.modules.project_gui.*",
        "ilastik.modules.project_gui.core.*",
        "ilastik.modules.project_gui.gui.*",
        "ilastik.modules.help.*",
        "ilastik.modules.help.core.*",
        "ilastik.modules.help.gui.*"
    ]
    has_ilastik = True
except ImportError:
    has_ilastik = False

cmdclass = {
        "install": Install,
        "test": Test
    }

if has_py2exe:
    cmdclass["py2exe"] = CPPy2Exe
    cmdclass["msi"] = CellProfilerMSI

setuptools.setup(
    author="cellprofiler-dev",
    author_email="cellprofiler-dev@broadinstitute.org",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: C",
        "Programming Language :: C++",
        "Programming Language :: Cython",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Topic :: Scientific/Engineering :: Image Recognition",
        "Topic :: Scientific/Engineering"
    ],
    cmdclass = cmdclass,
    console = [ 
        {
        "icon_resources": [
            (1, "artwork/CellProfilerIcon.ico")
            ],
        "script" : "CellProfiler.py"
        },
        {
            "icon_resources": [
                (1, "artwork/CellProfilerIcon.ico")
                ],
            "script" : "cellprofiler/analysis_worker.py"
            }],
    description="",
    entry_points={
        'console_scripts': [
            "cellprofiler=cellprofiler.__main__:main"
        ],
        'gui_scripts': [

        ]
    },
    include_package_data=True,
    install_requires=[
        "cellh5",
        "centrosome",
        "h5py",
        "javabridge",
        "libtiff",
        "matplotlib",
        "MySQL-python",
        "numpy",
        "pytest",
        "python-bioformats",
        "pyzmq",
        "scipy"
    ],
    keywords="",
    license="BSD",
    long_description="",
    name="cellprofiler",
    options = {
        "py2exe": {
            "dll_excludes": [
                "crypt32.dll",
                "iphlpapi.dll",
                "jvm.dll",
                "kernelbase.dll",
                "libzmq.pyd", # zmq 14.x must prevent renaming to zmq.libzmq
                "mpr.dll",
                "msasn1.dll",
                "msvcr90.dll",
                "msvcm90.dll",
                "msvcp90.dll",
                "nsi.dll",
                "uxtheme.dll",
                "vigranumpycore.pyd", # Same as libzmq.pyd - prevent rename
                "winnsi.dll"
                ],
            "excludes": [
                "Cython",
                "IPython",
                "pylab",
                "PyQt4.uic.port_v3", # python 3 -> 2 compatibility
                "Tkinter",
                "zmq.libzmq" # zmq 14.x added manually
                ],
            "includes": [
                "h5py", "h5py.*",
                "lxml", "lxml.*",
                "scipy.io.matlab.streams", "scipy.special", "scipy.special.*",
                "scipy.sparse.csgraph._validation",
                "skimage.draw", "skimage._shared.geometry", 
                "skimage.filters.rank.*",
                "sklearn.*", "sklearn.neighbors", "sklearn.neighbors.*",
                "sklearn.utils.*", "sklearn.utils.sparsetools.*"
                ] + zmq_includes + ilastik_includes,
            "packages": packages,
            "skip_archive": True
            }
    },
    package_data = {
        "artwork": glob.glob(os.path.join("artwork", "*"))
    },
    packages = packages + ["artwork"],
    setup_requires=[
        "clint",
        "matplotlib",
        "numpy",
        "pytest",
        "requests",
        "scipy",
        "pyzmq"
    ],
    url="https://github.com/CellProfiler/CellProfiler",
    version="2.2.0"
)
