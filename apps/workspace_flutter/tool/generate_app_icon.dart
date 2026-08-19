import 'dart:io';

import 'package:image/image.dart' as image;

void main() {
  final source = image.decodePng(
    File('assets/brand/geem-app-icon.png').readAsBytesSync(),
  );
  if (source == null) throw StateError('Could not decode Geem app icon.');

  final canvas = image.Image(width: 1024, height: 1024);
  image.fill(canvas, color: image.ColorRgb8(14, 47, 68));
  final mascot = image.copyResize(
    source,
    width: 860,
    height: 860,
    interpolation: image.Interpolation.cubic,
  );
  image.compositeImage(canvas, mascot, dstX: 82, dstY: 82);
  File(
    'assets/brand/geem-app-icon-opaque.png',
  ).writeAsBytesSync(image.encodePng(canvas));
}
