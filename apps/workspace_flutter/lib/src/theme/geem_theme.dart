import 'package:flutter/material.dart';

abstract final class GeemColors {
  static const brand = Color(0xFF0E2F44);
  static const brand2 = Color(0xFF214B68);
  static const accent = Color(0xFF367D9E);
  static const lightMuted = Color(0xFFF4F4F5);
  static const lightBorder = Color(0xFFE4E4E7);
  static const darkBackground = Color(0xFF09090B);
  static const darkMuted = Color(0xFF18181B);
  static const darkBorder = Color(0xFF27272A);
  static const amber = Color(0xFFFBBF24);
}

ThemeData geemLightTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: GeemColors.brand,
    brightness: Brightness.light,
    primary: GeemColors.brand,
    secondary: GeemColors.accent,
    surface: Colors.white,
  );
  return _baseTheme(scheme).copyWith(
    scaffoldBackgroundColor: Colors.white,
    cardColor: Colors.white,
    dividerColor: GeemColors.lightBorder,
  );
}

ThemeData geemDarkTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: GeemColors.accent,
    brightness: Brightness.dark,
    primary: GeemColors.accent,
    secondary: const Color(0xFF6AB6D8),
    surface: GeemColors.darkBackground,
  );
  return _baseTheme(scheme).copyWith(
    scaffoldBackgroundColor: GeemColors.darkBackground,
    cardColor: GeemColors.darkBackground,
    dividerColor: GeemColors.darkBorder,
  );
}

ThemeData _baseTheme(ColorScheme scheme) {
  final isDark = scheme.brightness == Brightness.dark;
  final border = isDark ? GeemColors.darkBorder : GeemColors.lightBorder;
  final muted = isDark ? GeemColors.darkMuted : GeemColors.lightMuted;
  final outline = OutlineInputBorder(
    borderRadius: BorderRadius.circular(12),
    borderSide: BorderSide(color: border),
  );
  return ThemeData(
    useMaterial3: true,
    fontFamily: 'IBM Plex Sans Arabic',
    colorScheme: scheme,
    visualDensity: VisualDensity.standard,
    splashFactory: InkSparkle.splashFactory,
    textTheme: const TextTheme(
      headlineMedium: TextStyle(fontWeight: FontWeight.w600, fontSize: 28),
      titleLarge: TextStyle(fontWeight: FontWeight.w600, fontSize: 20),
      titleMedium: TextStyle(fontWeight: FontWeight.w600, fontSize: 16),
      bodyLarge: TextStyle(fontSize: 16, height: 1.55),
      bodyMedium: TextStyle(fontSize: 14, height: 1.55),
      bodySmall: TextStyle(fontSize: 12, height: 1.45),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: isDark ? GeemColors.darkMuted : Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: outline,
      enabledBorder: outline,
      focusedBorder: outline.copyWith(
        borderSide: BorderSide(color: scheme.primary, width: 1.5),
      ),
      errorBorder: outline.copyWith(
        borderSide: BorderSide(color: scheme.error),
      ),
      focusedErrorBorder: outline.copyWith(
        borderSide: BorderSide(color: scheme.error, width: 1.5),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 44),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        side: BorderSide(color: border),
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: border),
      ),
    ),
    dividerTheme: DividerThemeData(color: border, thickness: 1, space: 1),
    dialogTheme: DialogThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    extensions: <ThemeExtension<dynamic>>[
      GeemThemeTokens(muted: muted, border: border),
    ],
  );
}

@immutable
class GeemThemeTokens extends ThemeExtension<GeemThemeTokens> {
  const GeemThemeTokens({required this.muted, required this.border});

  final Color muted;
  final Color border;

  @override
  GeemThemeTokens copyWith({Color? muted, Color? border}) => GeemThemeTokens(
    muted: muted ?? this.muted,
    border: border ?? this.border,
  );

  @override
  GeemThemeTokens lerp(covariant GeemThemeTokens? other, double t) {
    if (other == null) return this;
    return GeemThemeTokens(
      muted: Color.lerp(muted, other.muted, t)!,
      border: Color.lerp(border, other.border, t)!,
    );
  }
}

extension GeemThemeContext on BuildContext {
  GeemThemeTokens get geemTokens =>
      Theme.of(this).extension<GeemThemeTokens>()!;
}
