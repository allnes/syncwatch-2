package syncwatch.synchronization;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Small strict value codec for the bounded first-party IPC contract, with duplicate-key rejection. */
final class Json {
    private final String source;
    private int index;
    private Json(String source) { this.source = source; }
    static Object parse(String source) {
        Json parser = new Json(source);
        Object result = parser.value(1); parser.space();
        if (parser.index != source.length()) throw bad();
        return result;
    }
    static IllegalArgumentException bad() { return new IllegalArgumentException("malformed-json"); }
    private void space() { while (index < source.length() && " \r\n\t".indexOf(source.charAt(index)) >= 0) index++; }
    private boolean take(char c) { space(); if (index < source.length() && source.charAt(index) == c) { index++; return true; } return false; }
    private void need(char c) { if (!take(c)) throw bad(); }
    private Object value(int depth) {
        space(); if (depth > 8 || index >= source.length()) throw bad();
        char c = source.charAt(index);
        if (c == '"') return string();
        if (c == '{') {
            index++; Map<String, Object> result = new LinkedHashMap<>();
            if (take('}')) return result;
            do {
                String key = string(); need(':'); Object item = value(depth + 1);
                if (result.containsKey(key)) throw bad(); result.put(key, item);
                if (take('}')) return result;
            } while (take(','));
            throw bad();
        }
        if (c == '[') {
            index++; List<Object> result = new ArrayList<>(); if (take(']')) return result;
            do { result.add(value(depth + 1)); if (take(']')) return result; } while (take(','));
            throw bad();
        }
        for (String token : List.of("true", "false", "null")) if (source.startsWith(token, index)) {
            index += token.length(); return token.equals("null") ? null : Boolean.valueOf(token);
        }
        int start = index;
        while (index < source.length() && " \r\n\t,]}".indexOf(source.charAt(index)) < 0) index++;
        String token = source.substring(start, index);
        if (!token.matches("-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?")) throw bad();
        double number = Double.parseDouble(token); if (!Double.isFinite(number)) throw bad(); return number;
    }
    private String string() {
        need('"'); StringBuilder result = new StringBuilder(); boolean ended = false;
        while (index < source.length()) {
            char c = source.charAt(index++);
            if (c == '"') { ended = true; break; }
            if (c < 32) throw bad();
            if (c == '\\') {
                if (index >= source.length()) throw bad();
                c = source.charAt(index++);
                switch (c) {
                    case '"', '\\', '/' -> { }
                    case 'b' -> c = '\b'; case 'f' -> c = '\f'; case 'n' -> c = '\n'; case 'r' -> c = '\r'; case 't' -> c = '\t';
                    case 'u' -> {
                        if (index + 4 > source.length()) throw bad();
                        String hex = source.substring(index, index + 4);
                        if (!hex.matches("[0-9a-fA-F]{4}")) throw bad();
                        c = (char)Integer.parseInt(hex, 16); index += 4;
                    }
                    default -> throw bad();
                }
            }
            result.append(c);
        }
        if (!ended) throw bad();
        for (int i = 0; i < result.length(); i++) {
            char c = result.charAt(i);
            if (Character.isHighSurrogate(c)) {
                if (++i == result.length() || !Character.isLowSurrogate(result.charAt(i))) throw bad();
            } else if (Character.isLowSurrogate(c)) throw bad();
        }
        return result.toString();
    }
    static String write(Object value) {
        if (value == null) return "null";
        if (value instanceof Boolean || value instanceof Number) return value.toString();
        if (value instanceof String text) {
            StringBuilder result = new StringBuilder("\"");
            for (int i = 0; i < text.length(); i++) {
                char c = text.charAt(i);
                if (c == '"' || c == '\\') result.append('\\');
                if (c < 32) result.append(String.format("\\u%04x", (int)c)); else result.append(c);
            }
            return result.append('"').toString();
        }
        if (value instanceof Map<?, ?> map) {
            List<String> fields = new ArrayList<>();
            for (var field : map.entrySet()) {
                if (!(field.getKey() instanceof String)) throw bad();
                fields.add(write(field.getKey()) + ":" + write(field.getValue()));
            }
            return "{" + String.join(",", fields) + "}";
        }
        if (value instanceof List<?> list) return "[" + String.join(",", list.stream().map(Json::write).toList()) + "]";
        throw bad();
    }
    static Map<String, Object> object(Object value) {
        if (!(value instanceof Map<?, ?> map)) throw bad();
        Map<String, Object> result = new LinkedHashMap<>();
        for (var p : map.entrySet()) { if (!(p.getKey() instanceof String key)) throw bad(); result.put(key, p.getValue()); }
        return result;
    }
}
