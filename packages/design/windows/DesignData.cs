using System.Globalization;

namespace SyncWatch.Design;

public sealed record DesignNode(string Id, string Kind, Dictionary<string, string> Props, DesignNode[] Children);
public sealed record DesignEvent(string Action, string? Value = null, string? Payload = null);
public sealed record DesignContext
{
    public Dictionary<string, string> Values { get; init; } = new();
    public Dictionary<string, DesignContext[]> Collections { get; init; } = new();
    public DesignContext Merge(DesignContext child) => new() { Values = Values.Concat(child.Values).GroupBy(p => p.Key).ToDictionary(g => g.Key, g => g.Last().Value), Collections = Collections.Concat(child.Collections).GroupBy(p => p.Key).ToDictionary(g => g.Key, g => g.Last().Value) };
    public string Resolve(string source, string language)
    {
        if (source.StartsWith("= ", StringComparison.Ordinal)) return Expression(source[2..], language);
        if (source.StartsWith('$')) return Values.GetValueOrDefault(source[1..], "");
        if (source.StartsWith('@')) return SyncWatchLayouts.Values.GetValueOrDefault(source[1..], "");
        string value = System.Text.RegularExpressions.Regex.Replace(source, @"\{~([A-Za-z][A-Za-z0-9]*)\}", match => SyncWatchCopy.Text(match.Groups[1].Value, language));
        foreach (var pair in Values) value = value.Replace("{" + pair.Key + "}", pair.Value, StringComparison.Ordinal);
        return source.StartsWith('~') ? value.Length == 1 ? "" : SyncWatchCopy.Text(value[1..], language) : value;
    }
    private string Expression(string source, string language)
    {
        var stack = new Stack<string>();
        foreach (string token in source.Split(' ', StringSplitOptions.RemoveEmptyEntries))
        {
            if (token == "if")
            {
                if (stack.Count < 3) return "";
                var no = stack.Pop(); var yes = stack.Pop(); var condition = stack.Pop(); stack.Push(Flag(condition) ? yes : no);
            }
            else if (new[] { "+", "-", "*", "/", "min", "max", "==", ">=", ">", "<" }.Contains(token))
            {
                if (stack.Count < 2) return "";
                string right = stack.Pop(), left = stack.Pop(); double a = Number(left), b = Number(right);
                double value = token switch { "+" => a + b, "-" => a - b, "*" => a * b, "/" => b == 0 ? 0 : a / b, "min" => Math.Min(a, b), "max" => Math.Max(a, b), "==" => left == right ? 1 : 0, ">=" => a >= b ? 1 : 0, ">" => a > b ? 1 : 0, _ => a < b ? 1 : 0 };
                stack.Push((double.IsFinite(value) ? value : 0).ToString(CultureInfo.InvariantCulture));
            }
            else stack.Push(Resolve(token, language));
        }
        return stack.Count == 1 ? stack.Pop() : "";
    }
    public static double Number(string value) => double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var number) && double.IsFinite(number) ? number : 0;
    public static bool Flag(string value) => value == "true" || double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var number) && number == 1;
}
public sealed record DesignElement(string Id, string Kind, Dictionary<string, string> Props, DesignElement[] Children)
{
    public string Text(string key) => Props.GetValueOrDefault(key, "");
    public double Number(string key) => DesignContext.Number(Text(key));
    public bool Flag(string key) => DesignContext.Flag(Text(key));
}
public static class DesignTree
{
    public static DesignElement? Resolve(string component, DesignContext context, string language, double width, double height) => SyncWatchLayouts.Components.TryGetValue(component, out var source) ? Resolve(source, context, language, width, height) : null;
    public static DesignElement? Resolve(DesignNode source, DesignContext context, string language, double width, double height)
    {
        var ctx = context.Merge(new() { Values = new() { ["viewport.width"] = width.ToString(CultureInfo.InvariantCulture), ["viewport.height"] = height.ToString(CultureInfo.InvariantCulture) } });
        return Expand(source, ctx, language, source.Id, SyncWatchLayouts.Defaults).FirstOrDefault();
    }
    private static DesignElement[] Expand(DesignNode node, DesignContext ctx, string language, string path, IReadOnlyDictionary<string, string> inherited)
    {
        var raw = inherited.Concat(node.Props).GroupBy(p => p.Key).ToDictionary(g => g.Key, g => g.Last().Value);
        if (raw.TryGetValue("when", out var when) && !DesignContext.Flag(ctx.Resolve(when, language))) return [];
        var local = raw.TryGetValue("height", out var dimension) && dimension != "fill" ? ctx.Merge(new() { Values = new() { ["local.height"] = ctx.Resolve(dimension, language) } }) : ctx;
        var p = raw.ToDictionary(v => v.Key, v => local.Resolve(v.Value, language));
        string Get(string key) => p.GetValueOrDefault(key, "");
        if (node.Kind == "repeat") return ctx.Collections.GetValueOrDefault(Get("items"), []).SelectMany((item, index) => node.Children.SelectMany(child => Expand(child, ctx.Merge(item), language, path + "." + index + "." + child.Id, inherited))).ToArray();
        if (node.Kind == "include")
        {
            if (!SyncWatchLayouts.Components.TryGetValue(Get("component"), out var source)) return [];
            var props = source.Props.Concat(node.Props.Where(p => p.Key != "component")).GroupBy(p => p.Key).ToDictionary(g => g.Key, g => g.Last().Value);
            return Expand(source with { Props = props }, ctx, language, path + "." + source.Id, inherited);
        }
        if (node.Kind is "if" or "switch")
        {
            var child = node.Kind == "if" ? node.Children.ElementAtOrDefault(DesignContext.Flag(Get("condition")) ? 0 : 1) : node.Children.FirstOrDefault(n => n.Props.GetValueOrDefault("case") == Get("value") || DesignContext.Flag(n.Props.GetValueOrDefault("case", "")) && DesignContext.Flag(Get("value"))) ?? node.Children.FirstOrDefault(n => n.Props.GetValueOrDefault("case") == "default");
            if (child is null) return [];
            var layout = node.Props.Where(v => new[] { "width", "height", "minWidth", "minHeight", "maxWidth", "maxHeight" }.Contains(v.Key));
            child = child with { Props = child.Props.Concat(layout).GroupBy(v => v.Key).ToDictionary(g => g.Key, g => g.Last().Value) };
            return Expand(child, ctx, language, path + "." + child.Id, inherited);
        }
        var childStyle = raw.Where(p => new[] { "fontSize", "fontFamily", "foreground", "weight" }.Contains(p.Key)).ToDictionary(p => p.Key, p => p.Value);
        var children = node.Children.SelectMany(child => Expand(child, ctx, language, path + "." + child.Id, childStyle)).ToArray();
        if (node.Kind == "choice") children = ctx.Collections.GetValueOrDefault(Get("options"), []).Select((item, index) => new DesignElement(path + ".option" + index, "option", item.Values.Concat(new[] { new KeyValuePair<string, string>("label", ctx.Merge(item).Resolve("~{label}", language)) }).GroupBy(p => p.Key).ToDictionary(g => g.Key, g => g.Last().Value), [])).ToArray();
        string kind = node.Kind == "row" && p.ContainsKey("wrapAt") && DesignContext.Number(ctx.Values.GetValueOrDefault("viewport.width", "")) < DesignContext.Number(Get("wrapAt")) ? "column" : node.Kind;
        return [new(path, kind, p, children)];
    }
}
