// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.drag
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.key.*
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupProperties
import kotlin.math.cos
import kotlin.math.round
import kotlin.math.sin

internal fun rgba(value: Long) = Color(
    ((value shr 24) and 255).toFloat() / 255,
    ((value shr 16) and 255).toFloat() / 255,
    ((value shr 8) and 255).toFloat() / 255,
    (value and 255).toFloat() / 255,
)
private val gap get() = SyncWatchTokens.layoutPanelGap.dp


// Mechanical primitive adapter only. This source remains excluded until Linux build/license closure.
data class DesignNode(val id: String, val kind: String, val props: Map<String, String>, val children: List<DesignNode>)
data class DesignEvent(val action: String, val value: String? = null, val payload: String? = null)
data class DesignContext(val values: Map<String, String> = emptyMap(), val collections: Map<String, List<DesignContext>> = emptyMap()) {
    fun merge(child: DesignContext) = DesignContext(values + child.values, collections + child.collections)
    fun resolve(source: String, language: String): String {
        if (source.startsWith("= ")) return expression(source.substring(2), language)
        if (source.startsWith('$')) return values[source.substring(1)].orEmpty()
        if (source.startsWith('@')) return SyncWatchLayouts.values[source.substring(1)].orEmpty()
        var output = Regex("\\{~([A-Za-z][A-Za-z0-9]*)\\}").replace(source) { SyncWatchCopy.text(it.groupValues[1], language) }
        for ((key, value) in values) output = output.replace("{$key}", value)
        return if (source.startsWith('~')) if (output.length == 1) "" else SyncWatchCopy.text(output.substring(1), language) else output
    }
    private fun expression(source: String, language: String): String {
        val stack = mutableListOf<String>()
        for (token in source.split(' ').filter { it.isNotEmpty() }) {
            if (token == "if") {
                if (stack.size < 3) return ""
                val no = stack.removeAt(stack.lastIndex); val yes = stack.removeAt(stack.lastIndex); val condition = stack.removeAt(stack.lastIndex)
                stack += if (flag(condition)) yes else no
            } else if (token in setOf("+", "-", "*", "/", "min", "max", "==", ">=", ">", "<")) {
                if (stack.size < 2) return ""
                val right = stack.removeAt(stack.lastIndex); val left = stack.removeAt(stack.lastIndex); val a = number(left); val b = number(right)
                val value = when (token) { "+" -> a+b; "-" -> a-b; "*" -> a*b; "/" -> if (b == 0.0) 0.0 else a/b; "min" -> minOf(a,b); "max" -> maxOf(a,b); "==" -> if (left == right) 1.0 else 0.0; ">=" -> if (a >= b) 1.0 else 0.0; ">" -> if (a > b) 1.0 else 0.0; else -> if (a < b) 1.0 else 0.0 }
                stack += (value.takeIf { it.isFinite() } ?: 0.0).toString()
            } else stack += resolve(token, language)
        }
        return stack.singleOrNull().orEmpty()
    }
    companion object {
        fun number(value: String) = value.toDoubleOrNull()?.takeIf { it.isFinite() } ?: 0.0
        fun flag(value: String) = value == "true" || value.toDoubleOrNull() == 1.0
    }
}
data class DesignElement(val id: String, val kind: String, val props: Map<String, String>, val children: List<DesignElement>) {
    fun text(key: String) = props[key].orEmpty()
    fun number(key: String) = DesignContext.number(text(key))
    fun flag(key: String) = DesignContext.flag(text(key))
}
object DesignTree {
    fun resolve(component: String, context: DesignContext, language: String, width: Double, height: Double): DesignElement? = SyncWatchLayouts.components[component]?.let { resolve(it, context, language, width, height) }
    fun resolve(source: DesignNode, context: DesignContext, language: String, width: Double, height: Double): DesignElement? =
        expand(source, context.merge(DesignContext(mapOf("viewport.width" to width.toString(), "viewport.height" to height.toString()))), language, source.id, SyncWatchLayouts.defaults).firstOrNull()
    private fun expand(node: DesignNode, context: DesignContext, language: String, path: String, inherited: Map<String,String>): List<DesignElement> {
        val raw = inherited + node.props
        if (raw["when"]?.let { !DesignContext.flag(context.resolve(it,language)) } == true) return emptyList()
        val local = raw["height"]?.takeIf { it != "fill" }?.let { context.merge(DesignContext(mapOf("local.height" to context.resolve(it,language)))) } ?: context
        val p = raw.mapValues { local.resolve(it.value,language) }
        if (node.kind == "repeat") return context.collections[p["items"]].orEmpty().flatMapIndexed { index, item -> node.children.flatMap { expand(it,context.merge(item),language,"$path.$index.${it.id}",inherited) } }
        if (node.kind == "include") {
            val source = SyncWatchLayouts.components[p["component"]] ?: return emptyList()
            return expand(source.copy(props=source.props+node.props.filterKeys { it != "component" }),context,language,"$path.${source.id}",inherited)
        }
        if (node.kind == "if" || node.kind == "switch") {
            val child = if (node.kind == "if") node.children.getOrNull(if (DesignContext.flag(p["condition"].orEmpty())) 0 else 1)
                else node.children.firstOrNull { it.props["case"] == p["value"] || DesignContext.flag(it.props["case"].orEmpty()) && DesignContext.flag(p["value"].orEmpty()) } ?: node.children.firstOrNull { it.props["case"] == "default" }
            child ?: return emptyList()
            return expand(child.copy(props=child.props+node.props.filterKeys { it in setOf("width","height","minWidth","minHeight","maxWidth","maxHeight") }),context,language,"$path.${child.id}",inherited)
        }
        val childStyle = raw.filterKeys { it in setOf("fontSize","fontFamily","foreground","weight") }
        val children = if (node.kind == "choice") context.collections[p["options"]].orEmpty().mapIndexed { index, option -> DesignElement("$path.option$index","option",option.values + ("label" to context.merge(option).resolve("~{label}",language)),emptyList()) }
            else node.children.flatMap { expand(it,context,language,"$path.${it.id}",childStyle) }
        val kind = if (node.kind == "row" && p.containsKey("wrapAt") && DesignContext.number(context.values["viewport.width"].orEmpty()) < DesignContext.number(p["wrapAt"].orEmpty())) "column" else node.kind
        return listOf(DesignElement(path,kind,p,children))
    }
}
private fun designColor(value: String, theme: SyncWatchTheme): Color {
    if (value.startsWith("theme.")) return SyncWatchLayouts.themeColor(value.substring(6),theme)?.let(::rgba) ?: Color.Transparent
    val color = if (value.startsWith('@')) SyncWatchLayouts.values[value.substring(1)].orEmpty() else value
    return color.removePrefix("#").takeIf { color.startsWith('#') && it.length == 8 }?.toLongOrNull(16)?.let(::rgba) ?: Color.Transparent
}
private fun designWeight(value: String) = when(value) { "heavy" -> FontWeight.Black; "bold" -> FontWeight.Bold; "semibold" -> FontWeight.SemiBold; else -> FontWeight.Normal }
private fun textStyle(n: DesignElement, theme: SyncWatchTheme) = TextStyle(color=designColor(n.text("foreground"),theme),fontSize=n.number("fontSize").sp,fontWeight=designWeight(n.text("weight")))
private fun Modifier.designFrame(n: DesignElement, theme: SyncWatchTheme): Modifier {
    var m=this.offset(n.number("offsetX").dp,n.number("offsetY").dp)
    if (n.text("width")=="fill") m=m.fillMaxWidth() else if (n.props.containsKey("width")) m=m.width(n.number("width").dp)
    if (n.text("height")=="fill") m=m.fillMaxHeight() else if (n.props.containsKey("height")) m=m.height(n.number("height").dp)
    if (n.props.containsKey("minWidth")) m=m.widthIn(min=n.number("minWidth").dp)
    if (n.props.containsKey("minHeight")) m=m.heightIn(min=n.number("minHeight").dp)
    val radius=if(n.text("radius")=="circle") maxOf(n.number("width"),n.number("height"))/2 else n.number("radius")
    val shape=RoundedCornerShape(radius.dp)
    m=m.clip(shape)
    if (n.text("gradient").isNotEmpty()) m=m.drawBehind {
        fun point(source:String):Offset {val v=source.split(',').map{DesignContext.number(it)};return Offset((v.getOrElse(0){0.0}*size.width).toFloat(),(v.getOrElse(1){0.0}*size.height).toFloat())}
        val stops=n.text("gradient").split('|').zip(n.text("gradientOffsets").split('|')).map{DesignContext.number(it.second).toFloat() to designColor(it.first,theme)}.toTypedArray()
        drawRect(androidx.compose.ui.graphics.Brush.linearGradient(*stops,start=point(n.text("gradientStart")),end=point(n.text("gradientEnd"))))
    }
    else if(n.text("background").isNotEmpty()) {
        val fill=designColor(n.text("background"),theme)
        val opacity=(if(n.props.containsKey("backgroundOpacity")) n.number("backgroundOpacity") else 1.0).toFloat().coerceIn(0f,1f)
        m=m.background(fill.copy(alpha=fill.alpha*opacity),shape)
    }
    if(n.number("borderWidth")>0) m=m.border(n.number("borderWidth").dp,designColor(n.text("border"),theme),shape)
    return m.padding(horizontal=(n.number("padding")+n.number("paddingX")).dp,vertical=(n.number("padding")+n.number("paddingY")).dp)
}
@Composable fun DesignSurface(component: String, context: DesignContext=DesignContext(), language: String="en", theme: SyncWatchTheme=SyncWatchTheme.dark,
    modifier: Modifier=Modifier, slots: Map<String,@Composable BoxScope.() -> Unit> = emptyMap(), onEvent:(DesignEvent)->Unit={}) {
    val source=SyncWatchLayouts.components[component] ?: return
    DesignNodeSurface(source,context,language,theme,modifier,slots,onEvent)
}

// Render a supplied document root through the same primitive adapter as registered components.
// Internal visibility permits the shared geometry corpus without another layout implementation.
@Composable internal fun DesignNodeSurface(source: DesignNode, context: DesignContext=DesignContext(), language: String="en",
    theme: SyncWatchTheme=SyncWatchTheme.dark, modifier: Modifier=Modifier,
    slots: Map<String,@Composable BoxScope.() -> Unit> = emptyMap(), onEvent:(DesignEvent)->Unit={}) {
    var frame=modifier
    for(key in listOf("width","height","minWidth","minHeight")) source.props[key]?.takeIf { it!="fill" }?.let {
        val n=DesignContext.number(context.resolve(it,language)).dp
        frame=when(key){"width"->frame.width(n);"height"->frame.height(n);"minWidth"->frame.widthIn(min=n);else->frame.heightIn(min=n)}
    }
    BoxWithConstraints(frame) {
        DesignTree.resolve(source,context,language,maxWidth.value.toDouble(),maxHeight.value.toDouble())?.let { RenderDesignNode(it,theme,slots,onEvent) }
    }
}
@Composable private fun RenderDesignNode(n:DesignElement,theme:SyncWatchTheme,slots:Map<String,@Composable BoxScope.()->Unit>,onEvent:(DesignEvent)->Unit,modifier:Modifier=Modifier) {
    val enabled=!n.props.containsKey("enabled")||n.flag("enabled")
    val currentEvent by rememberUpdatedState(onEvent)
    val currentNode by rememberUpdatedState(n)
    fun emit(value:String?=null) { if(enabled) currentEvent(DesignEvent(n.text("action"),value?:n.props["value"],n.props["payload"])) }
    val frame=modifier.designFrame(n,theme).semantics { if(n.text("label").isNotEmpty()) contentDescription=n.text("label"); if(n.flag("selected")) selected=true }
    when(n.kind){
        "row"->Row(frame,verticalAlignment=if(n.text("align")=="top") Alignment.Top else Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(n.number("gap").dp,if(n.text("align")=="trailing") Alignment.End else if(n.text("align")=="center") Alignment.CenterHorizontally else Alignment.Start)) {
            n.children.forEach { c->key(c.id){RenderDesignNode(c,theme,slots,onEvent,if(c.text("width")=="fill"||c.kind=="spacer") Modifier.weight(1f) else Modifier)} }
        }
        "column"->Column(frame,verticalArrangement=Arrangement.spacedBy(n.number("gap").dp),horizontalAlignment=if(n.text("align")=="center") Alignment.CenterHorizontally else Alignment.Start) {
            n.children.forEach { c->key(c.id){RenderDesignNode(c,theme,slots,onEvent,if(c.text("height")=="fill"||c.kind=="spacer") Modifier.weight(1f) else Modifier)} }
        }
        "overlay"->Box(frame,contentAlignment=Alignment.Center){n.children.forEach { c->key(c.id){RenderDesignNode(c,theme,slots,onEvent)} }}
        "scroll"->Column(frame.verticalScroll(rememberScrollState())){n.children.forEach{RenderDesignNode(it,theme,slots,onEvent)}}
        "spacer"->Spacer(modifier)
        "line"->Box(modifier.then(if(n.text("axis")=="vertical") Modifier.width(n.number("thickness").dp).then(if(n.props.containsKey("length"))Modifier.height(n.number("length").dp)else Modifier.fillMaxHeight()) else Modifier.height(n.number("thickness").dp).then(if(n.props.containsKey("length"))Modifier.width(n.number("length").dp)else Modifier.fillMaxWidth())).background(designColor(n.text("background"),theme)))
        "text"->{
            val density=LocalDensity.current.density
            val move=if(n.text("moveAction").isNotEmpty()) Modifier.pointerInput(n.text("moveAction"),density){awaitEachGesture {val down=awaitFirstDown();var total=Offset.Zero;drag(down.id){change->total+=change.position-change.previousPosition;change.consume();currentEvent(DesignEvent(n.text("moveAction"),"${total.x/density},${total.y/density}"))};currentEvent(DesignEvent(n.text("moveAction")))}} else Modifier
            // BasicText fills its requested frame but lays its paragraph at the top.
            // Keep the frame on a generic container so document alignment places
            // the intrinsic paragraph, matching the native adapters.
            val alignment=when(n.text("align")) { "top"->Alignment.TopStart; "leading"->Alignment.CenterStart; "trailing"->Alignment.CenterEnd; else->Alignment.Center }
            Box(frame.then(move),contentAlignment=alignment) {
                BasicText(n.text("text"),style=textStyle(n,theme).copy(textAlign=if(n.text("align")=="center") TextAlign.Center else TextAlign.Start),maxLines=if(n.props.containsKey("lines")) n.number("lines").toInt() else Int.MAX_VALUE,overflow=TextOverflow.Ellipsis)
            }
        }
        "icon"->Canvas(frame){for(p in SyncWatchLayouts.assets[n.text("name")].orEmpty()){val path=Path();for(i in p.indices step 2){val x=p[i]/SyncWatchLayouts.coordinateSize*size.width;val y=p[i+1]/SyncWatchLayouts.coordinateSize*size.height;if(i==0)path.moveTo(x,y)else path.lineTo(x,y)};path.close();drawPath(path,designColor(n.text("foreground"),theme))}}
        "button"->Box(modifier.alpha(if(enabled)1f else n.number("disabledOpacity").toFloat()).clickable(enabled=enabled,role=Role.Button){emit()}.designFrame(n,theme),contentAlignment=if(n.text("contentAlign")=="leading")Alignment.CenterStart else Alignment.Center){
            if(n.children.isEmpty())BasicText(n.props["text"]?:n.text("label"),style=textStyle(n,theme))else n.children.forEach{RenderDesignNode(it,theme,slots,onEvent)}
        }
        "input"->BasicTextField(n.text("value"),{emit(it)},frame.alpha(if(enabled)1f else n.number("disabledOpacity").toFloat()),enabled=enabled,textStyle=textStyle(n,theme),singleLine=true,decorationBox={inner->Box(Modifier.fillMaxSize(),contentAlignment=Alignment.CenterStart){if(n.text("value").isEmpty())BasicText(n.text("label"),style=textStyle(n,theme).copy(color=designColor(n.text("placeholderFill"),theme)));inner()}})
        "choice"->{
            var open by remember {mutableStateOf(false)};var measured by remember {mutableStateOf(androidx.compose.ui.unit.IntSize.Zero)}
            val selected=n.children.firstOrNull{it.text("id")==n.text("value")}
            Box(frame.onSizeChanged{measured=it}.alpha(if(enabled)1f else n.number("disabledOpacity").toFloat()).clickable(enabled=enabled,role=Role.Button){open=true},contentAlignment=Alignment.CenterStart){
                BasicText(selected?.text("label")?:n.text("value"),style=textStyle(n,theme))
                Canvas(Modifier.align(Alignment.CenterEnd).size(n.number("markWidth").dp,n.number("markHeight").dp)){for(p in SyncWatchLayouts.assets[n.text("markName")].orEmpty()){val path=Path();for(i in p.indices step 2){val x=p[i]/SyncWatchLayouts.coordinateSize*size.width;val y=p[i+1]/SyncWatchLayouts.coordinateSize*size.height;if(i==0)path.moveTo(x,y)else path.lineTo(x,y)};path.close();drawPath(path,designColor(n.text("markFill"),theme))}}
                if(open)Popup(offset=IntOffset(0,measured.height),onDismissRequest={open=false},properties=PopupProperties(focusable=true)){
                    val density=LocalDensity.current
                    Column(Modifier.width(with(density){measured.width.toDp()}).background(designColor(n.text("rowFill"),theme)).border(n.number("borderWidth").dp,designColor(n.text("border"),theme))){n.children.forEach{o->BasicText(o.text("label"),Modifier.fillMaxWidth().clickable{emit(o.text("id"));open=false}.padding(horizontal=n.number("rowPaddingX").dp,vertical=n.number("rowPaddingY").dp),style=textStyle(n,theme))}}
                }
            }
        }
        "toggle"->Row(frame.alpha(if(enabled)1f else n.number("disabledOpacity").toFloat()).clickable(enabled=enabled,role=Role.Switch){emit((!n.flag("value")).toString())}.semantics{toggleableState=if(n.flag("value"))androidx.compose.ui.state.ToggleableState.On else androidx.compose.ui.state.ToggleableState.Off},verticalAlignment=Alignment.CenterVertically){
            BasicText(n.text("text"),Modifier.weight(1f),style=textStyle(n,theme));Box(Modifier.size(n.number("trackWidth").dp,n.number("trackHeight").dp).background(designColor(n.text(if(n.flag("value"))"onFill" else "offFill"),theme),RoundedCornerShape((n.number("trackHeight")/2).dp)),contentAlignment=if(n.flag("value"))Alignment.CenterEnd else Alignment.CenterStart){Box(Modifier.padding(horizontal=n.number("thumbInset").dp).size(n.number("thumbSize").dp).background(designColor(n.text("thumbFill"),theme),RoundedCornerShape((n.number("thumbSize")/2).dp)))}
        }
        "gesture"->{
            val density=LocalDensity.current.density
            fun publish(dx:Double,dy:Double,ox:Double=n.number("originWidth"),oy:Double=n.number("originHeight")) {
                if(!enabled)return
                val extent=n.text("gestureMode")=="extent"
                val x=if(extent)(ox+dx).coerceIn(n.number("minimumX"),n.number("maximumX"))else dx
                val y=if(extent)(oy+dy).coerceIn(n.number("minimumY"),n.number("maximumY"))else dy
                emit("$x,$y")
            }
            Box(frame.onKeyEvent { e->
                val step=n.number("gestureStep")
                if(!enabled||e.type!=KeyEventType.KeyDown)false else when(e.key){Key.DirectionLeft->{publish(-step,0.0);true};Key.DirectionRight->{publish(step,0.0);true};Key.DirectionUp->{publish(0.0,-step);true};Key.DirectionDown->{publish(0.0,step);true};else->false}
            }.focusable(enabled).semantics{if(enabled)customActions=listOf(CustomAccessibilityAction(n.text("label")){publish(n.number("gestureStep"),if(n.text("gestureMode")=="extent")n.number("gestureStep")else 0.0);true})}
            .pointerInput(enabled,density){if(enabled)awaitEachGesture{
                val down=awaitFirstDown();var total=Offset.Zero
                val ox=currentNode.number("originWidth");val oy=currentNode.number("originHeight")
                drag(down.id){change->val delta=change.position-change.previousPosition;total+=delta;change.consume();val v=if(n.text("gestureMode")=="extent")total else delta;publish((v.x/density).toDouble(),(v.y/density).toDouble(),ox,oy)}
            }},contentAlignment=Alignment.Center){n.children.forEach{RenderDesignNode(it,theme,slots,onEvent)}}
        }
        "range"->DesignRange(n,theme,modifier){emit(it.toString())}
        "slot"->Box(frame,contentAlignment=Alignment.Center){slots[n.text("name")]?.invoke(this)}
        "subtitle"->DesignSubtitle(n,theme,modifier)
    }
}
@Composable private fun DesignRange(n:DesignElement,theme:SyncWatchTheme,modifier:Modifier,onChange:(Double)->Unit){
    val enabled=!n.props.containsKey("enabled")||n.flag("enabled");val min=n.number("minimum");val max=maxOf(min,n.number("maximum"));val value=n.number("value").coerceIn(min,max)
    val current by rememberUpdatedState(onChange)
    fun update(v:Double){if(enabled)current(if(n.flag("round"))round(v.coerceIn(min,max))else v.coerceIn(min,max))}
    Canvas(modifier.then(if(n.text("width")=="fill"||!n.props.containsKey("width"))Modifier.fillMaxWidth()else Modifier.width(n.number("width").dp)).height(n.number("height").dp).alpha(if(enabled)1f else n.number("disabledOpacity").toFloat())
        .semantics{contentDescription=n.text("label");progressBarRangeInfo=ProgressBarRangeInfo(value.toFloat(),min.toFloat()..max.toFloat());if(!enabled)disabled();setProgress{if(enabled){update(it.toDouble());true}else false}}
        .onKeyEvent{if(!enabled||it.type!=KeyEventType.KeyDown)false else when(it.key){Key.DirectionLeft,Key.DirectionDown->{update(value-n.number("step"));true};Key.DirectionRight,Key.DirectionUp->{update(value+n.number("step"));true};Key.MoveHome->{update(min);true};Key.MoveEnd->{update(max);true};else->false}}.focusable(enabled)
        .pointerInput(enabled,min,max){if(enabled)awaitEachGesture{fun updateAt(x:Float){update(min+(x/size.width.coerceAtLeast(1))*(max-min))};val down=awaitFirstDown();down.consume();updateAt(down.position.x);drag(down.id){change->change.consume();updateAt(change.position.x)}}}){
        val fraction=((value-min)/(max-min).coerceAtLeast(1.0)).toFloat();val y=size.height/2
        drawLine(designColor(n.text("trackFill"),theme),Offset(0f,y),Offset(size.width,y),n.number("trackHeight").dp.toPx());drawLine(designColor(n.text("progressFill"),theme),Offset(0f,y),Offset(size.width*fraction,y),n.number("trackHeight").dp.toPx());drawCircle(designColor(n.text("thumbFill"),theme),(n.number("thumbSize")/2).dp.toPx(),Offset(size.width*fraction,y))
    }
}
@Composable private fun DesignSubtitle(n:DesignElement,theme:SyncWatchTheme,modifier:Modifier){
    var measured by remember{mutableStateOf(0)};val density=LocalDensity.current
    val family=when(n.text("fontFamily")){"serif"->FontFamily.Serif;"monospace"->FontFamily.Monospace;else->FontFamily.Default}
    val style=textStyle(n,theme).copy(fontFamily=family,textAlign=TextAlign.Center)
    Box(modifier.fillMaxWidth().height(n.number("height").dp).clip(RoundedCornerShape(0.dp)).background(designColor(n.text("background"),theme))){
        Box(Modifier.fillMaxWidth().padding(horizontal=n.number("textPaddingX").dp).offset(y=(n.number("centerY")-with(density){measured.toDp().value}/2).dp).onSizeChanged{measured=it.height},contentAlignment=Alignment.Center){
            val count=n.number("outlineSamples").toInt().coerceAtLeast(1)
            repeat(count){index->BasicText(n.text("text"),Modifier.offset((cos(index*Math.PI*2/count)*n.number("outlineWidth")).dp,(sin(index*Math.PI*2/count)*n.number("outlineWidth")).dp),style=style.copy(color=designColor(n.text("outline"),theme)),maxLines=n.number("lines").toInt())}
            BasicText(n.text("text"),style=style,maxLines=n.number("lines").toInt())
        }
    }
}
