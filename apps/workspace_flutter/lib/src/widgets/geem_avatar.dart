import 'package:flutter/material.dart';

class GeemAvatar extends StatelessWidget {
  const GeemAvatar({this.size = 40, this.heroTag, super.key});

  final double size;
  final Object? heroTag;

  @override
  Widget build(BuildContext context) {
    final image = ClipRRect(
      borderRadius: BorderRadius.circular(size * 0.28),
      child: Image.asset(
        'assets/brand/geem-avatar.webp',
        width: size,
        height: size,
        fit: BoxFit.cover,
        filterQuality: FilterQuality.high,
      ),
    );
    return heroTag == null ? image : Hero(tag: heroTag!, child: image);
  }
}
