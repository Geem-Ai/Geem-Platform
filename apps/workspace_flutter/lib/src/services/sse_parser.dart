import 'dart:convert';

class SseEvent {
  const SseEvent({required this.event, required this.data});

  final String event;
  final Object? data;

  Map<String, dynamic> get dataMap => data is Map
      ? Map<String, dynamic>.from(data! as Map)
      : const <String, dynamic>{};
}

/// Incremental SSE parser that tolerates arbitrary UTF-8 chunk boundaries and
/// both LF and CRLF line endings.
class SseParser {
  String _buffer = '';
  String _event = 'message';
  final List<String> _dataLines = [];

  List<SseEvent> addChunk(String chunk) {
    _buffer += chunk;
    final events = <SseEvent>[];
    var newline = _buffer.indexOf('\n');
    while (newline >= 0) {
      var line = _buffer.substring(0, newline);
      _buffer = _buffer.substring(newline + 1);
      if (line.endsWith('\r')) line = line.substring(0, line.length - 1);
      final event = _consumeLine(line);
      if (event != null) events.add(event);
      newline = _buffer.indexOf('\n');
    }
    return events;
  }

  List<SseEvent> close() {
    final events = <SseEvent>[];
    if (_buffer.isNotEmpty) {
      var line = _buffer;
      if (line.endsWith('\r')) line = line.substring(0, line.length - 1);
      final event = _consumeLine(line);
      if (event != null) events.add(event);
      _buffer = '';
    }
    final finalEvent = _dispatch();
    if (finalEvent != null) events.add(finalEvent);
    return events;
  }

  SseEvent? _consumeLine(String line) {
    if (line.isEmpty) return _dispatch();
    if (line.startsWith(':')) return null;
    if (line.startsWith('event:')) {
      _event = line.substring(6).trim();
    } else if (line.startsWith('data:')) {
      var value = line.substring(5);
      if (value.startsWith(' ')) value = value.substring(1);
      _dataLines.add(value);
    }
    return null;
  }

  SseEvent? _dispatch() {
    if (_dataLines.isEmpty) {
      _event = 'message';
      return null;
    }
    final raw = _dataLines.join('\n');
    Object? data = raw;
    try {
      data = jsonDecode(raw);
    } on FormatException {
      // Plain-text SSE data is valid and intentionally retained.
    }
    final result = SseEvent(
      event: _event.isEmpty ? 'message' : _event,
      data: data,
    );
    _event = 'message';
    _dataLines.clear();
    return result;
  }
}
