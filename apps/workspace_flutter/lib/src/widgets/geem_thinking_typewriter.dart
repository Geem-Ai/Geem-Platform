import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// A small blinking caret that can be used beside thinking or streamed text.
///
/// The pulse is disabled when the platform requests reduced motion. The caret
/// remains visible in that case, so it never disappears as a status cue.
class PulsingCursor extends StatefulWidget {
  const PulsingCursor({
    super.key,
    this.width = 1,
    this.height = 14,
    this.margin = const EdgeInsetsDirectional.only(start: 2),
    this.color,
    this.duration = const Duration(milliseconds: 1000),
  }) : assert(width > 0),
       assert(height > 0);

  final double width;
  final double height;
  final EdgeInsetsGeometry margin;
  final Color? color;
  final Duration duration;

  @override
  State<PulsingCursor> createState() => _PulsingCursorState();
}

class _PulsingCursorState extends State<PulsingCursor>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  bool? _motionDisabled;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(duration: widget.duration, vsync: this);
    _opacity = Tween<double>(
      begin: 0.5,
      end: 1,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _syncMotionPreference();
  }

  @override
  void didUpdateWidget(covariant PulsingCursor oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.duration != widget.duration) {
      _controller.duration = widget.duration;
    }
  }

  void _syncMotionPreference() {
    final disabled = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    if (_motionDisabled == disabled) return;
    _motionDisabled = disabled;
    if (disabled) {
      _controller
        ..stop()
        ..value = 1;
    } else {
      _controller
        ..value = 1
        ..repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: Padding(
      padding: widget.margin,
      child: FadeTransition(
        opacity: _opacity,
        child: ColoredBox(
          color:
              widget.color ??
              DefaultTextStyle.of(context).style.color ??
              Theme.of(context).colorScheme.onSurface,
          child: SizedBox(width: widget.width, height: widget.height),
        ),
      ),
    ),
  );
}

/// Cycles through Geem's thinking statuses with Workspace Web's typewriter
/// cadence.
///
/// Messages are shuffled once when this widget mounts. Set [shuffleMessages]
/// to false for a fixed order (useful in deterministic tests). Animated text
/// is excluded from accessibility updates; assistive technology receives the
/// stable [semanticsLabel] as a polite live-region status instead.
class GeemThinkingTypewriter extends StatefulWidget {
  const GeemThinkingTypewriter({
    super.key,
    required this.messages,
    required this.semanticsLabel,
    this.active = true,
    this.shuffleMessages = true,
    this.style,
    this.cursorColor,
  });

  static const typingDuration = Duration(milliseconds: 28);
  static const holdDuration = Duration(milliseconds: 1600);
  static const deleteDuration = Duration(milliseconds: 16);
  static const gapDuration = Duration(milliseconds: 280);

  final List<String> messages;
  final String semanticsLabel;
  final bool active;
  final bool shuffleMessages;
  final TextStyle? style;
  final Color? cursorColor;

  @override
  State<GeemThinkingTypewriter> createState() => _GeemThinkingTypewriterState();
}

class _GeemThinkingTypewriterState extends State<GeemThinkingTypewriter> {
  final Random _random = Random();

  Timer? _timer;
  late List<String> _messages;
  int _messageIndex = 0;
  int _visibleRuneCount = 0;
  bool? _motionDisabled;
  bool _started = false;

  @override
  void initState() {
    super.initState();
    _messages = _prepareMessages(widget.messages);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final disabled = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    if (!_started || _motionDisabled != disabled) {
      _motionDisabled = disabled;
      _started = true;
      _restart();
    }
  }

  @override
  void didUpdateWidget(covariant GeemThinkingTypewriter oldWidget) {
    super.didUpdateWidget(oldWidget);
    final messagesChanged = !listEquals(oldWidget.messages, widget.messages);
    final shuffleChanged = oldWidget.shuffleMessages != widget.shuffleMessages;
    if (messagesChanged || shuffleChanged) {
      _messages = _prepareMessages(widget.messages);
    }
    if (messagesChanged ||
        shuffleChanged ||
        oldWidget.active != widget.active) {
      _restart();
    }
  }

  List<String> _prepareMessages(List<String> source) {
    final result = source.where((message) => message.isNotEmpty).toList();
    if (!widget.shuffleMessages) return result;
    for (var index = result.length - 1; index > 0; index -= 1) {
      final swapIndex = _random.nextInt(index + 1);
      final current = result[index];
      result[index] = result[swapIndex];
      result[swapIndex] = current;
    }
    return result;
  }

  void _restart() {
    _timer?.cancel();
    _messageIndex = 0;
    _visibleRuneCount = 0;
    if (!widget.active || _messages.isEmpty) return;
    if (_motionDisabled ?? false) {
      _visibleRuneCount = _currentRunes.length;
      _schedule(GeemThinkingTypewriter.holdDuration, _showNextReducedMotion);
    } else {
      _schedule(GeemThinkingTypewriter.typingDuration, _typeNextRune);
    }
  }

  List<int> get _currentRunes => _messages[_messageIndex].runes.toList();

  String get _visibleText {
    if (_messages.isEmpty) return '';
    final runes = _currentRunes;
    return String.fromCharCodes(runes.take(_visibleRuneCount));
  }

  void _schedule(Duration duration, VoidCallback callback) {
    _timer?.cancel();
    _timer = Timer(duration, () {
      if (!mounted || !widget.active || _messages.isEmpty) return;
      callback();
    });
  }

  void _typeNextRune() {
    final runes = _currentRunes;
    if (_visibleRuneCount < runes.length) {
      setState(() => _visibleRuneCount += 1);
    }
    if (_visibleRuneCount >= runes.length) {
      if (_messages.length > 1) {
        _schedule(GeemThinkingTypewriter.holdDuration, _beginDeleting);
      }
    } else {
      _schedule(GeemThinkingTypewriter.typingDuration, _typeNextRune);
    }
  }

  void _beginDeleting() {
    _schedule(GeemThinkingTypewriter.deleteDuration, _deleteNextRune);
  }

  void _deleteNextRune() {
    if (_visibleRuneCount > 0) {
      setState(() => _visibleRuneCount -= 1);
    }
    if (_visibleRuneCount <= 0) {
      _schedule(GeemThinkingTypewriter.gapDuration, _beginNextMessage);
    } else {
      _schedule(GeemThinkingTypewriter.deleteDuration, _deleteNextRune);
    }
  }

  void _beginNextMessage() {
    setState(() {
      _messageIndex = (_messageIndex + 1) % _messages.length;
      _visibleRuneCount = 0;
    });
    _schedule(GeemThinkingTypewriter.typingDuration, _typeNextRune);
  }

  void _showNextReducedMotion() {
    setState(() {
      _messageIndex = (_messageIndex + 1) % _messages.length;
      _visibleRuneCount = _currentRunes.length;
    });
    _schedule(GeemThinkingTypewriter.holdDuration, _showNextReducedMotion);
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.active || _messages.isEmpty) return const SizedBox.shrink();
    final effectiveStyle = widget.style ?? DefaultTextStyle.of(context).style;
    return Semantics(
      container: true,
      liveRegion: true,
      label: widget.semanticsLabel,
      child: ExcludeSemantics(
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_visibleText, style: effectiveStyle),
            PulsingCursor(color: widget.cursorColor ?? effectiveStyle.color),
          ],
        ),
      ),
    );
  }
}
