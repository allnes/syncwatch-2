// Apache-2.0. Compile the single neutral component tree; formatters contain no screen designs.
const q = JSON.stringify;
export const layoutKinds = new Set(['row','column','overlay','text','button','icon','input','choice','toggle','range','line','spacer','scroll','slot','subtitle','repeat','include','if','switch','gesture','retained']);
export function validateLayouts(spec, tokens, copy, inputs) {
    if (spec.schemaVersion !== 1 || (!Number.isFinite(spec.coordinateSize) || spec.coordinateSize <= 0 || spec.coordinateSize > 65536) || !spec.components || !spec.styles || !spec.controls) throw Error('Invalid design document');
    const numeric = new Set('width height minWidth minHeight maxWidth maxHeight gap length padding paddingX paddingY radius focusRadius focusWidth lines minScale fontSize borderWidth disabledOpacity pressedOpacity backgroundOpacity trackWidth trackHeight thumbSize thumbInset markWidth markHeight markInset rowPaddingX rowPaddingY thickness outlineWidth outlineSamples textPaddingX centerY minimum maximum step wrapAt offsetX offsetY tabIndex barWidth thumbMinimum thumbRadius gestureStep minimumX minimumY maximumX maximumY originWidth originHeight'.split(' '));
    const known = new Set([...numeric, ...'foreground background border focusBorder hoverBorder gradient gradientStart gradientEnd gradientOffsets weight fontFamily align contentAlign axis truncate outline clip cycleFocus selected text label name action payload value automation shortcut options items component condition when case round enabled moveAction trackFill progressFill thumbFill onFill offFill markName markFill rowFill rowHighlight rowForeground placeholderFill labelAutomation blockInput gestureMode presented secret popoverSlot popoverEdge popoverDismiss'.split(' ')]);
    const roles = new Set(Object.keys(inputs.themes.themes.dark));
    const colorKeys = new Set('foreground background border outline focusBorder hoverBorder trackFill progressFill thumbFill onFill offFill markFill rowFill rowHighlight rowForeground placeholderFill'.split(' '));
    const operators = new Set(['+','-','*','/','min','max','==','>=','>','<','if']);
    const ids = new Set(); let count = 0;
    function properties(props) {
        for (const [key,value] of Object.entries(props)) {
            if (!known.has(key) || typeof value !== 'string' || value.length > 4096 || /[\u0000-\u001f]/.test(value)) throw Error('Invalid design property');
            for (const match of value.matchAll(/@([a-zA-Z][\w.]*)/g)) if (!tokens.has(match[1])) throw Error('Unknown design token '+match[1]);
            for (const match of value.matchAll(/theme\.([A-Za-z][\w]*)/g)) if (!roles.has(match[1])) throw Error('Unknown semantic color role');
            if (value.startsWith('= ')) {
                let depth=0;
                for (const token of value.slice(2).split(' ').filter(Boolean)) {
                    if (operators.has(token)) { const arity=token==='if'?3:2; if(depth<arity) throw Error('Malformed design expression'); depth-=arity-1; }
                    else depth++;
                }
                if(depth!==1) throw Error('Malformed design expression');
            } else if (numeric.has(key) && !value.startsWith('$') && !value.startsWith('@') && !['fill','circle'].includes(value)) {
                if(!value.trim() || !Number.isFinite(Number(value))) throw Error('Nonfinite design dimension');
            }
            if (colorKeys.has(key) && value.startsWith('@') && !value.startsWith('@color.')) throw Error('Expected a color token');

            if (value.startsWith('~') && !value.includes('{') && value.length > 1 && !Object.hasOwn(copy.locales.en,value.slice(1))) throw Error('Unknown design copy '+value);
        }
    }
    for (const props of [...Object.values(spec.styles),...Object.values(spec.controls),spec.defaults]) properties(props);
    function visit(node,depth=0) {
        if (depth > 32 || ++count > 2048 || !node || !/^[A-Za-z][\w]*$/.test(node.id) || ids.has(node.id) || !layoutKinds.has(node.kind)) throw Error('Invalid/duplicate design node');
        ids.add(node.id);
        if (Object.keys(node).some(k=>!['id','kind','styles','props','children'].includes(k)) || !Array.isArray(node.children) || !Array.isArray(node.styles)) throw Error('Unexpected design node fields');
        for (const style of node.styles) if (!Object.hasOwn(spec.styles,style)) throw Error('Unknown design style');
        properties(node.props);
        if (node.props.popoverSlot !== undefined && (node.kind !== 'button' || !/^[A-Za-z][A-Za-z0-9]*$/.test(node.props.popoverSlot)
            || !['top','bottom'].includes(node.props.popoverEdge) || typeof node.props.popoverDismiss !== 'string'
            || !/^[A-Za-z][A-Za-z0-9]*$/.test(node.props.popoverDismiss))) throw Error('Invalid native popover binding');
        if (node.kind === 'gesture' && !['delta','extent'].includes(node.props.gestureMode)) throw Error('Invalid gesture coordinate mode');
        if (node.kind === 'include' && !Object.hasOwn(spec.components,node.props.component)) throw Error('Unknown design component');
        if (['repeat','scroll','gesture','retained'].includes(node.kind) && node.children.length !== 1) throw Error('Expected one content template');
        if (node.kind === 'retained' && !Object.hasOwn(node.props,'presented')) throw Error('Retained content requires presentation state');
        if (node.kind === 'if' && (node.children.length < 1 || node.children.length > 2)) throw Error('Invalid design condition');
        for (const child of node.children) visit(child,depth+1);
    }
    Object.values(spec.components).forEach(n=>visit(n));
    // Includes must be acyclic. A native slot is a bounded host-owned leaf, never a screen implementation.
    function includes(name,chain=[]) {
        if (chain.includes(name)) throw Error('Recursive design component');
        function walk(n) { if(n.kind==='include') includes(n.props.component,[...chain,name]); n.children.forEach(walk); }
        walk(spec.components[name]);
    }
    Object.keys(spec.components).forEach(n=>includes(n));
    for (const [key,paths] of Object.entries(spec.assets)) if (!/^[A-Za-z][\w.]*$/.test(key) || !Array.isArray(paths) || !paths.length || paths.some(p=>p.length<6||p.length%2||p.some(v=>!Number.isFinite(v)||v<0||v>spec.coordinateSize))) throw Error('Invalid design asset');
}
export function compileLayouts(s, values, player, themes, call) {
    function node(n) { return {id:n.id,kind:n.kind,props:{...s.controls.common,...s.controls[n.kind],...Object.fromEntries(n.styles.flatMap(k=>Object.entries(s.styles[k]))),...n.props},children:n.children.map(node)}; }
    return {themeRoles:Object.keys(themes.themes.dark),schemaVersion:s.schemaVersion,coordinateSize:s.coordinateSize,defaults:s.defaults,tokens:values,controls:s.controls,assets:{...s.assets,...Object.fromEntries(Object.entries(call?.icons ?? {}).map(([k,v])=>['call.'+k,v])),...Object.fromEntries(Object.entries(player.icons).map(([k,v])=>['player.'+k,v]))},components:Object.fromEntries(Object.entries(s.components).map(([k,v])=>[k,node(v)]))};
}
function bottomUp(node,write) { const children=node.children.map(n=>bottomUp(n,write)); write(node,children); return node.id; }
export function swiftLayouts(spec, digest) {
    let out='\npublic enum SyncWatchLayouts {\n    public static let sourceDigest = '+q(digest)+'\n';
    out+='    public static let coordinateSize = '+spec.coordinateSize+(Number.isInteger(spec.coordinateSize)?'.0':'')+'\n';
    out+='    public static func themeColor(_ role: String, theme: SyncWatchTheme) -> Color? {\n        switch role {\n'+spec.themeRoles.map(k=>'        case '+q(k)+': theme.'+k+'\n').join('')+'        default: nil\n        }\n    }\n';
    for (const [name,dict] of Object.entries({defaults:spec.defaults,values:spec.tokens})) out+='    public static let '+name+': [String: String] = [\n'+Object.entries(dict).map(([k,v])=>'        '+q(k)+': '+q(String(v))+',\n').join('')+'    ]\n';
    out+='    public static let assets: [String: [[Double]]] = [\n'+Object.entries(spec.assets).map(([k,v])=>'        '+q(k)+': [\n'+v.map(p=>'            [\n'+p.map(n=>'                '+n+',\n').join('')+'            ]'+(v.length===1?'\n':',\n')).join('')+'        ],\n').join('')+'    ]\n';
    out+='    public static let components: [String: DesignNode] = [\n'+Object.keys(spec.components).map(k=>'        '+q(k)+': make'+k+'(),\n').join('')+'    ]\n';
    for (const [k,tree] of Object.entries(spec.components)) {
        out+='    private static func make'+k+'() -> DesignNode {\n';
        bottomUp(tree,(n,children)=>{out+='        let '+n.id+' = DesignNode(\n            id: '+q(n.id)+', kind: '+q(n.kind)+',\n            props: [\n'+Object.entries(n.props).map(([p,v])=>{const line='                '+q(p)+': '+q(v)+',';return line.length>120?'                '+q(p)+':\n                    '+q(v)+',\n':line+'\n';}).join('')+'            ],\n'+(('            children: ['+children.join(', ')+'])').length>120?'            children: [\n'+children.map(id=>'                '+id+',\n').join('')+'            ])\n':'            children: ['+children.join(', ')+'])\n');});
        out+='        return '+tree.id+'\n    }\n';
    }
    return out+'}\n';
}
export function csharpLayouts(spec,digest) {
    let out='\npublic static class SyncWatchLayouts\n{\n    public const string SourceDigest = '+q(digest)+';\n    public const double CoordinateSize = '+spec.coordinateSize+';\n';
    for (const [name,dict] of Object.entries({Defaults:spec.defaults,Values:spec.tokens})) out+='    public static System.Collections.Generic.IReadOnlyDictionary<string, string> '+name+' { get; } = new System.Collections.Generic.Dictionary<string, string>\n    {\n'+Object.entries(dict).map(([k,v])=>'        ['+q(k)+'] = '+q(String(v))+',\n').join('')+'    };\n';
    out+='    public static System.Collections.Generic.IReadOnlyDictionary<string, double[][]> Assets { get; } = new System.Collections.Generic.Dictionary<string, double[][]>\n    {\n'+Object.entries(spec.assets).map(([k,v])=>'        ['+q(k)+'] = '+q(v)+',\n').join('')+'    };\n';
    out+='    public static System.Collections.Generic.IReadOnlyDictionary<string, DesignNode> Components { get; } = new System.Collections.Generic.Dictionary<string, DesignNode>\n    {\n'+Object.keys(spec.components).map(k=>'        ['+q(k)+'] = Make'+k+'(),\n').join('')+'    };\n';
    for (const [k,tree] of Object.entries(spec.components)) {
        out+='    private static DesignNode Make'+k+'()\n    {\n';
        bottomUp(tree,(n,children)=>{out+='        var '+n.id+' = new DesignNode('+q(n.id)+', '+q(n.kind)+', new()\n        {\n'+Object.entries(n.props).map(([p,v])=>'            ['+q(p)+'] = '+q(v)+',\n').join('')+'        }, ['+children.join(', ')+']);\n';});
        out+='        return '+tree.id+';\n    }\n';
    }
    return out+'}\n';
}
export function kotlinLayouts(spec,digest) {
    const kq=s=>q(s).replaceAll('$','\\$');
    let out='\nobject SyncWatchLayouts {\n    const val sourceDigest = '+kq(digest)+'\n    const val coordinateSize = '+spec.coordinateSize+(Number.isInteger(spec.coordinateSize)?'.0f':'f')+'\n';
    out+='    fun themeColor(role: String, theme: SyncWatchTheme): Long? = when (role) {\n'+spec.themeRoles.map(k=>'        '+kq(k)+' -> theme.'+k+'\n').join('')+'        else -> null\n    }\n';
    for (const [name,dict] of Object.entries({defaults:spec.defaults,values:spec.tokens})) out+='    val '+name+' = mapOf(\n'+Object.entries(dict).map(([k,v])=>'        '+kq(k)+' to '+kq(String(v))+',\n').join('')+'    )\n';
    out+='    val assets = mapOf(\n'+Object.entries(spec.assets).map(([k,v])=>'        '+kq(k)+' to listOf('+v.map(p=>'listOf('+p.map(n=>n+(Number.isInteger(n)?'.0f':'f')).join(', ')+')').join(', ')+'),\n').join('')+'    )\n';
    out+='    val components = mapOf(\n'+Object.keys(spec.components).map(k=>'        '+kq(k)+' to make'+k+'(),\n').join('')+'    )\n';
    for (const [k,tree] of Object.entries(spec.components)) {
        out+='    private fun make'+k+'(): DesignNode {\n';
        bottomUp(tree,(n,children)=>{out+='        val '+n.id+' = DesignNode('+kq(n.id)+', '+kq(n.kind)+', mapOf(\n'+Object.entries(n.props).map(([p,v])=>'            '+kq(p)+' to '+kq(v)+',\n').join('')+'        ), listOf('+children.join(', ')+'))\n';});
        out+='        return '+tree.id+'\n    }\n';
    }
    return out+'}\n';
}
