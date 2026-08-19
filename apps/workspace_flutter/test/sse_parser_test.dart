import 'package:flutter_test/flutter_test.dart';
import 'package:geem_workspace/src/services/sse_parser.dart';

void main() {
  test('parses chunked CRLF SSE events and JSON payloads', () {
    final parser = SseParser();
    final events = <SseEvent>[];

    events.addAll(parser.addChunk('event: message_start\r'));
    events.addAll(parser.addChunk('\ndata: {"user_message_id":"u1"}\r\n\r'));
    events.addAll(
      parser.addChunk('\nevent: token\ndata: {"text":"مرحباً"}\n\n'),
    );
    events.addAll(parser.close());

    expect(events, hasLength(2));
    expect(events.first.event, 'message_start');
    expect(events.first.dataMap['user_message_id'], 'u1');
    expect(events.last.event, 'token');
    expect(events.last.dataMap['text'], 'مرحباً');
  });

  test('joins multiline data and preserves plain text', () {
    final parser = SseParser();
    final events = parser.addChunk(
      'event: message\ndata: first\ndata: second\n\n',
    );

    expect(events.single.event, 'message');
    expect(events.single.data, 'first\nsecond');
  });
}
