import os
import sys
from glob import glob

import cpuinfo
from Cython.Distutils.build_ext import new_build_ext as build_ext
from setuptools import Extension, setup
from setuptools.errors import CCompilerError, ExecError, PlatformError
from distutils import ccompiler
from distutils.command.clean import clean

# determine CPU support for SSE2 and AVX2
cpu_info = cpuinfo.get_cpu_info()
flags = cpu_info.get('flags', [])
have_sse2 = 'sse2' in flags
have_avx2 = 'avx2' in flags

# MARK: - Eugo add flags for NEON and ACLE
have_neon = 'neon' in flags
have_acle = 'acle' in flags

disable_sse2 = 'DISABLE_NUMCODECS_SSE2' in os.environ
disable_avx2 = 'DISABLE_NUMCODECS_AVX2' in os.environ

# setup common compile arguments
have_cflags = 'CFLAGS' in os.environ
base_compile_args = []
if have_cflags:
    # respect compiler options set by user
    pass
elif os.name == 'posix':
    if disable_sse2:
        base_compile_args.append('-mno-sse2')
    elif have_sse2:
        base_compile_args.append('-msse2')
    if disable_avx2:
        base_compile_args.append('-mno-avx2')
    elif have_avx2:
        base_compile_args.append('-mavx2')
    # @HELP - # MARK: - Eugo add append flags for NEON and ACE
    elif have_neon:
        base_compile_args.append("-march=armv8-a -mtune=cortex-a72 -moutline-atomics")
    elif have_acle:
        base_compile_args.append("-march=armv8-a -mtune=cortex-a72 -moutline-atomics")

# On macOS, force libc++ in case the system tries to use `stdlibc++`.
# The latter is often absent from modern macOS systems.
if sys.platform == 'darwin':
    base_compile_args.append('-stdlib=libc++')


def info(*msg):
    kwargs = dict(file=sys.stdout)
    print('[numcodecs]', *msg, **kwargs)


def error(*msg):
    kwargs = dict(file=sys.stderr)
    print('[numcodecs]', *msg, **kwargs)


def blosc_extension():
    info('setting up Blosc extension')

    extra_compile_args = base_compile_args.copy()
    define_macros = []

    # Don't use the bundled blosc sources; we use our system libraries
    blosc_sources = []
    include_dirs = []

    # @HELP
    # blosc_sources = [f for f in glob('c-blosc/blosc/*.c') if 'avx2' not in f and 'sse2' not in f]
    # include_dirs = [os.path.join('c-blosc', 'blosc')]

    # MARK: - Don't use the bundled blosc sources; we use our system libraries
    # blosc_sources += glob('c-blosc/internal-complibs/lz4*/*.c')
    # blosc_sources += glob('c-blosc/internal-complibs/snappy*/*.cc')
    # blosc_sources += glob('c-blosc/internal-complibs/zlib*/*.c')
    # blosc_sources += glob('c-blosc/internal-complibs/zstd*/common/*.c')
    # blosc_sources += glob('c-blosc/internal-complibs/zstd*/compress/*.c')
    # blosc_sources += glob('c-blosc/internal-complibs/zstd*/decompress/*.c')
    # blosc_sources += glob('c-blosc/internal-complibs/zstd*/dictBuilder/*.c')
    include_dirs += [d for d in glob('c-blosc/internal-complibs/*') if os.path.isdir(d)]
    include_dirs += [d for d in glob('c-blosc/internal-complibs/*/*') if os.path.isdir(d)]
    include_dirs += [d for d in glob('c-blosc/internal-complibs/*/*/*') if os.path.isdir(d)]
    # remove minizip because Python.h 3.8 tries to include crypt.h
    include_dirs = [d for d in include_dirs if 'minizip' not in d]

    # Add system include directories
    include_dirs += "/usr"
    include_dirs += "/usr/local"

    define_macros += [
        ('HAVE_LZ4', 1),
        # Change to default include snappy
        # @HELP
        ('HAVE_SNAPPY', 1),
        ('HAVE_ZLIB', 1),
        ('HAVE_ZSTD', 1),
    ]
    # define_macros += [('CYTHON_TRACE', '1')]

    # MARK: - SSE2
    if have_sse2 and not disable_sse2:
        info('compiling Blosc extension with SSE2 support')
        extra_compile_args.append('-DSHUFFLE_SSE2_ENABLED')
        # @HELP
        # blosc_sources += [f for f in glob('c-blosc/blosc/*.c') if 'sse2' in f]
        if os.name == 'nt':
            define_macros += [('__SSE2__', 1)]
    else:
        info('compiling Blosc extension without SSE2 support')

    # MARK: - AVX2
    if have_avx2 and not disable_avx2:
        info('compiling Blosc extension with AVX2 support')
        extra_compile_args.append('-DSHUFFLE_AVX2_ENABLED')
        # @HELP
        # blosc_sources += [f for f in glob('c-blosc/blosc/*.c') if 'avx2' in f]
        if os.name == 'nt':
            define_macros += [('__AVX2__', 1)]
    else:
        info('compiling Blosc extension without AVX2 support')

    # MARK: - NEON
    # @HELP
    if have_neon:
        info('compiling Blosc extension with NEON support')
        extra_compile_args.append('-DNEON_INTRINSICS')
        # blosc_sources += [f for f in glob('c-blosc/blosc/*.c') if 'neon' in f]
    else:
        info('compiling Blosc extension without NEON support')

    # MARK: - ACLE
    # @HELP
    if have_acle:
        info('compiling Blosc extension with ACLE support')
        extra_compile_args.append('-DARM_ACLE')
        # blosc_sources += [f for f in glob('c-blosc/blosc/*.c') if 'acle' in f]
    else:
        info('compiling Blosc extension without acle support')

    # include assembly files
    if cpuinfo.platform.machine() == 'x86_64':
        extra_objects = [
            S[:-1] + 'o' for S in glob("c-blosc/internal-complibs/zstd*/decompress/*amd64.S")
        ]
    else:
        extra_objects = []

    # MARK: - Add numcodecs/blosc, numcodecs/zlib, and numcodecs/snappy sources
    sources = ['numcodecs/blosc.pyx']

    # define extension module
    extensions = [
        Extension(
            'numcodecs.blosc',
            sources=sources + blosc_sources,
            include_dirs=include_dirs,
            define_macros=define_macros,
            extra_compile_args=extra_compile_args,
            extra_objects=extra_objects,
            # MARK: - Add Blosc library for linker to look for
            libraries=["blosc", "snappy", "zlib"],
        ),
    ]

    return extensions


def zstd_extension():
    info('setting up Zstandard extension')

    zstd_sources = []
    extra_compile_args = base_compile_args.copy()
    include_dirs = []
    define_macros = []

    # MARK: - Don't use the bundled zstd sources; we use our system libraries
    # zstd_sources += glob('c-blosc/internal-complibs/zstd*/common/*.c')
    # zstd_sources += glob('c-blosc/internal-complibs/zstd*/compress/*.c')
    # zstd_sources += glob('c-blosc/internal-complibs/zstd*/decompress/*.c')
    # zstd_sources += glob('c-blosc/internal-complibs/zstd*/dictBuilder/*.c')

    include_dirs += [d for d in glob('c-blosc/internal-complibs/zstd*') if os.path.isdir(d)]
    include_dirs += [d for d in glob('c-blosc/internal-complibs/zstd*/*') if os.path.isdir(d)]

    # MARK: - Add system include directories
    include_dirs += "/usr"
    include_dirs += "/usr/local"
    # define_macros += [('CYTHON_TRACE', '1')]

    # MARK: - Add numcodecs/zstd sources
    sources = ['numcodecs/zstd.pyx']

    # include assembly files
    if cpuinfo.platform.machine() == 'x86_64':
        extra_objects = [
            S[:-1] + 'o' for S in glob("c-blosc/internal-complibs/zstd*/decompress/*amd64.S")
        ]
    else:
        extra_objects = []

    # define extension module
    extensions = [
        Extension(
            'numcodecs.zstd',
            sources=sources + zstd_sources,
            include_dirs=include_dirs,
            define_macros=define_macros,
            extra_compile_args=extra_compile_args,
            extra_objects=extra_objects,
            # MARK: - Add ZSTD library for linker to look for
            libraries=["zstd"],
        ),
    ]

    return extensions


def lz4_extension():
    info('setting up LZ4 extension')

    extra_compile_args = base_compile_args.copy()
    define_macros = []
    lz4_sources = []

    # MARK: - Don't use the bundled lz4 sources; we use our system libraries
    # lz4_sources = glob('c-blosc/internal-complibs/lz4*/*.c')
    include_dirs = [d for d in glob('c-blosc/internal-complibs/lz4*') if os.path.isdir(d)]
    include_dirs += ['numcodecs']

    # MARK: - Add system include directories
    include_dirs += "/usr"
    include_dirs += "/usr/local"
    # define_macros += [('CYTHON_TRACE', '1')]

    # MARK: - Add numcodecs/lz4 sources
    sources = ['numcodecs/lz4.pyx']

    # define extension module
    extensions = [
        Extension(
            'numcodecs.lz4',
            sources=sources + lz4_sources,
            include_dirs=include_dirs,
            define_macros=define_macros,
            extra_compile_args=extra_compile_args,
            # MARK: - Add lz4 library for linker to look for
            libraries=["lz4"],
        ),
    ]

    return extensions


def vlen_extension():
    info('setting up vlen extension')
    import numpy

    extra_compile_args = base_compile_args.copy()
    define_macros = []

    # setup sources
    include_dirs = ['numcodecs', numpy.get_include()]
    # define_macros += [('CYTHON_TRACE', '1')]

    sources = ['numcodecs/vlen.pyx']

    # define extension module
    extensions = [
        Extension(
            'numcodecs.vlen',
            sources=sources,
            include_dirs=include_dirs,
            define_macros=define_macros,
            extra_compile_args=extra_compile_args,
        ),
    ]

    return extensions


def fletcher_extension():
    info('setting up fletcher32 extension')

    extra_compile_args = base_compile_args.copy()
    define_macros = []

    # setup sources
    include_dirs = ['numcodecs']
    # define_macros += [('CYTHON_TRACE', '1')]

    sources = ['numcodecs/fletcher32.pyx']

    # define extension module
    extensions = [
        Extension(
            'numcodecs.fletcher32',
            sources=sources,
            include_dirs=include_dirs,
            define_macros=define_macros,
            extra_compile_args=extra_compile_args,
        ),
    ]

    return extensions


def jenkins_extension():
    info('setting up jenkins extension')

    extra_compile_args = base_compile_args.copy()
    define_macros = []

    # setup sources
    include_dirs = ['numcodecs']
    define_macros += [('CYTHON_TRACE', '1')]

    sources = ['numcodecs/jenkins.pyx']

    # define extension module
    extensions = [
        Extension(
            'numcodecs.jenkins',
            sources=sources,
            include_dirs=include_dirs,
            define_macros=define_macros,
            extra_compile_args=extra_compile_args,
        ),
    ]

    return extensions


def compat_extension():
    info('setting up compat extension')

    extra_compile_args = base_compile_args.copy()

    sources = ['numcodecs/compat_ext.pyx']

    # define extension module
    extensions = [
        Extension(
            'numcodecs.compat_ext',
            sources=sources,
            extra_compile_args=extra_compile_args,
        ),
    ]

    return extensions


def shuffle_extension():
    info('setting up shuffle extension')

    extra_compile_args = base_compile_args.copy()

    sources = ['numcodecs/_shuffle.pyx']

    # define extension module
    extensions = [
        Extension('numcodecs._shuffle', sources=sources, extra_compile_args=extra_compile_args),
    ]

    return extensions


if sys.platform == 'win32':
    ext_errors = (CCompilerError, ExecError, PlatformError, IOError, ValueError)
else:
    ext_errors = (CCompilerError, ExecError, PlatformError)


class BuildFailed(Exception):
    pass


class ve_build_ext(build_ext):
    # This class allows C extension building to fail.

    def run(self):
        try:
            if cpuinfo.platform.machine() == 'x86_64':
                S_files = glob('c-blosc/internal-complibs/zstd*/decompress/*amd64.S')
                compiler = ccompiler.new_compiler()
                compiler.src_extensions.append('.S')
                compiler.compile(S_files)

            build_ext.run(self)
        except PlatformError as e:
            error(e)
            raise BuildFailed()

    def build_extension(self, ext):
        try:
            build_ext.build_extension(self, ext)
        except ext_errors as e:
            error(e)
            raise BuildFailed()


class Sclean(clean):
    # Clean up .o files created by .S files

    def run(self):
        if cpuinfo.platform.machine() == 'x86_64':
            o_files = glob('c-blosc/internal-complibs/zstd*/decompress/*amd64.o')
            for f in o_files:
                os.remove(f)

        clean.run(self)


def run_setup(with_extensions):
    if with_extensions:
        ext_modules = (
            blosc_extension()
            + zstd_extension()
            + lz4_extension()
            + compat_extension()
            + shuffle_extension()
            + vlen_extension()
            + fletcher_extension()
            + jenkins_extension()
        )

        cmdclass = dict(build_ext=ve_build_ext, clean=Sclean)
    else:
        ext_modules = []
        cmdclass = {}

    setup(
        ext_modules=ext_modules,
        cmdclass=cmdclass,
    )


if __name__ == '__main__':
    is_pypy = hasattr(sys, 'pypy_translation_info')
    with_extensions = not is_pypy and 'DISABLE_NUMCODECS_CEXT' not in os.environ
    run_setup(with_extensions)
