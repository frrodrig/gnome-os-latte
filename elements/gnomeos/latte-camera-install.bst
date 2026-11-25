kind: import

sources:
- kind: local
  path: files/gnomeos/latte-camera-install.py

depends:
- freedesktop-sdk.bst:components/python3.bst

config:
  target: /usr/bin
