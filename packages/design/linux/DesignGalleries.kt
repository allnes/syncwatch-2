// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.runtime.*
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.ui.geometry.Offset

@Composable fun DesignGallery() = DesignFixtureGallery("library")
@Composable fun SettingsGallery() = DesignFixtureGallery("settings")
@Composable fun PlayerGallery() = DesignFixtureGallery("player")
@Composable fun CallGallery() = DesignFixtureGallery("call")
@Composable fun PlayerSettingsGallery() = DesignFixtureGallery("playerSettings")

// Fixture observations and event wiring only; all gallery/modal composition is declarative.
@Composable private fun DesignFixtureGallery(subject:String) {
    var language by remember{mutableStateOf("en")};var dark by remember{mutableStateOf(true)};var failSave by remember{mutableStateOf(false)}
    var section by remember{mutableStateOf(if(subject=="settings")"interface"else"playback")}
    var state by remember{mutableStateOf(if(subject=="library")"selected"else if(subject=="player")"paused"else if(subject=="call")"ready"else"editing")}
    var lastAction by remember{mutableStateOf("")};var modalOpen by remember{mutableStateOf(false)};var modalOffset by remember{mutableStateOf(Offset.Zero)}
    var library by remember{mutableStateOf(LibraryPresentation.gallery(LibraryVisualState.selected))}
    var call by remember{mutableStateOf(CallPresentation.gallery(SyncWatchCall.galleryCases[2]))}
    var player by remember{mutableStateOf(PlayerPresentation.gallery(PlayerVisualState.paused))}
    var settings by remember{mutableStateOf(SettingsEditor(editableFields=SyncWatchSettings.defaults.keys,canSave=true))}
    var editor by remember{mutableStateOf(PlayerSettingsEditor(editableFields=SyncWatchPlayerSettings.defaults.keys,canSave=true))}
    var saved by remember{mutableStateOf(SyncWatchPlayerSettings.defaults.toMap())}
    val theme=if(dark)SyncWatchTheme.dark else SyncWatchTheme.light
    fun choice(id:String,value:String,options:List<String>)=DesignContext(mapOf("id" to id,"label" to "gallery"+id.replaceFirstChar{it.uppercase()},"kind" to "choice","value" to value,"editable" to (!modalOpen).toString()),mapOf("options" to options.map{DesignContext(mapOf("id" to it,"label" to it))}))
    fun toggle(id:String,value:Boolean)=DesignContext(mapOf("id" to id,"label" to "gallery"+id.replaceFirstChar{it.uppercase()},"kind" to "boolean","value" to value.toString(),"editable" to (!modalOpen).toString()))
    val states=when(subject){"library"->SyncWatchCopy.galleryStates;"settings"->SyncWatchSettings.states;"player"->SyncWatchPlayer.states;"call"->SyncWatchCall.galleryCases.map{it.id};else->SyncWatchPlayerSettings.states}
    val sections=when(subject){"settings"->SyncWatchSettings.sections;"playerSettings"->SyncWatchPlayerSettings.sections;else->emptyList()}
    val controls=mutableListOf(choice("state",state,states));if(sections.isNotEmpty())controls+=choice("section",section,sections)
    controls+=choice("language",language,listOf("en","ru"));controls+=toggle("dark",dark);if(subject=="settings"||subject=="playerSettings")controls+=toggle("failSave",failSave)
    val context=DesignContext(mapOf("lastAction" to lastAction,"modalOpen" to modalOpen.toString(),"modalOffsetX" to modalOffset.x.toString(),"modalOffsetY" to modalOffset.y.toString()),mapOf("galleryControls" to controls))
    val content:@Composable BoxScope.()->Unit={when(subject){
        "library"->LibraryWorkspace(library,language,theme){action,value->lastAction=action;if(action=="selectMovie")library=library.copy(selectedID=value)}
        "settings"->key(section){SettingsDialog(settings,{settings=it},language,section,theme,onSave={!failSave})}
        "playerSettings"->key(section){PlayerSettingsDialog(editor,{editor=it},language,section,theme,onSave={!failSave})}
        "call"->DesignSurface("callFixture",language=language,theme=theme,slots=mapOf("callFixtureContent" to {
            CallWindowShell(call,language,theme,remoteSurface={DesignSurface("callRemoteFixture",language=language,theme=theme)},localPreview={DesignSurface("callLocalFixture",language=language,theme=theme)}){request->lastAction=request.action;call=call.applyingFixture(request)}
        }))
        else->PlayerChrome(if(modalOpen)player.copy(enabledActions=emptySet())else player,language,theme,videoSurface={DesignSurface("fixtureVideo",DesignContext(mapOf("fixtureLabel" to "playerFixture")),language,theme)}){action,value->
            lastAction=action
            when(action){"seek"->player=player.copy(positionMs=value!!.toLong());"playPause"->player=player.copy(state=if(player.playing)PlayerVisualState.paused else PlayerVisualState.playing);"setMovieVolume"->player=player.copy(volume=value!!);"muteMovie"->player=player.copy(muted=!player.muted);"openPlayerSettings"->{editor=PlayerSettingsEditor(saved,SyncWatchPlayerSettings.defaults.keys,true);modalOffset=Offset.Zero;modalOpen=true}}
        }
    }}
    val modal:@Composable BoxScope.()->Unit={PlayerSettingsDialog(editor,{editor=it},language,theme=theme,onSave={values->saved=values.toMap();player=player.copy(skipSeconds=values.getValue("skipSeconds").toInt(),volume=values.getValue("defaultVolume").toDouble()/100);true},onClose={modalOpen=false},onMove={modalOffset+=it})}
    DesignSurface("Gallery",context,language,theme,slots=mapOf("galleryContent" to content,"modalContent" to modal)){event->
        if(event.action=="gallery"&&!modalOpen&&event.payload!=null&&event.value!=null)when(event.payload){
            "language"->language=event.value;"dark"->dark=event.value=="true";"failSave"->failSave=event.value=="true";"section"->section=event.value
            "state"->{state=event.value;when(subject){"library"->library=LibraryPresentation.gallery(LibraryVisualState.valueOf(state));"call"->call=CallPresentation.gallery(SyncWatchCall.galleryCases.single{it.id==state});"player"->player=PlayerPresentation.gallery(PlayerVisualState.valueOf(state));"settings"->settings=SettingsEditor(editableFields=SyncWatchSettings.defaults.keys,canSave=true,state=SettingsVisualState.valueOf(state));"playerSettings"->editor=PlayerSettingsEditor(editableFields=SyncWatchPlayerSettings.defaults.keys,canSave=state!="readOnly",state=PlayerSettingsVisualState.valueOf(state))}}
        }
    }
}
