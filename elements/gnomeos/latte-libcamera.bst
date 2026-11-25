# SPDX-FileCopyrightText: Freedesktop-SDK Developers
# SPDX-License-Identifier: MIT
#
# Based on components/libcamera.bst from Freedesktop SDK 114ae909ec9881958bd507c8b4414aa33f758d2b.
kind: meson

build-depends:
- freedesktop-sdk.bst:public-stacks/buildsystem-cmake.bst
- freedesktop-sdk.bst:public-stacks/buildsystem-meson.bst

depends:
- freedesktop-sdk.bst:components/glib.bst
- freedesktop-sdk.bst:components/gstreamer-plugins-base.bst
- freedesktop-sdk.bst:components/gstreamer.bst
- freedesktop-sdk.bst:components/libevent.bst
- freedesktop-sdk.bst:components/libyaml.bst
- freedesktop-sdk.bst:components/python3-jinja2.bst
- freedesktop-sdk.bst:components/python3-ply.bst
- freedesktop-sdk.bst:components/python3-pyyaml.bst
- freedesktop-sdk.bst:components/systemd-libs.bst

variables:
  pipelines: 'auto'
  meson-build: ninja -v -j%{max-jobs} -C %{build-dir}
  meson-global: --buildtype=plain -Dauto_features=enabled -Db_pie=true -Ddefault_library=shared -Db_lto=true -Db_lto_threads=${LTOJOBS}
  meson-local: >-
    -Dgstreamer=enabled
    -Dpipelines=%{pipelines}
    -Dudev=enabled
    -Dv4l2=true
    -Dtracing=disabled
    -Dtest=false
    -Dlc-compliance=disabled
    -Dqcam=disabled
    -Ddocumentation=disabled
    -Dpycamera=disabled
    -Dcam-output-sdl2=disabled

environment:
  LTOJOBS: '%{max-jobs}'

environment-nocache:
- LTOJOBS

public:
  bst:
    split-rules:
      devel:
        (>):
        - '%{prefix}/lib/*.a'

sources:
- kind: git_repo
  url: latte_libcamera:libcamera/libcamera.git
  ref: v0.7.2-0-g191e202178f02430b5942397c70d215cdd2056fa
- kind: patch
  path: patches/latte-camera/disable-ipa-sign.patch
- kind: patch
  path: patches/latte-camera/atomisp.patch
- kind: git_module
  path: subprojects/libyuv
  url: latte_chromium:libyuv/libyuv.git
  ref: 500f45652c459cfccd20f83f297eb66cb7b015cb
