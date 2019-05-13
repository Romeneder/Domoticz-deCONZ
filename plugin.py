# deCONZ Bridge
#
# Author: Smanar
#
"""
<plugin key="deCONZ" name="deCONZ plugin" author="Smanar" version="1.0.9" wikilink="https://github.com/Smanar/Domoticz-deCONZ" externallink="https://www.dresden-elektronik.de/funktechnik/products/software/pc-software/deconz/?L=1">
    <description>
        <br/><br/>
        <h2>deCONZ Bridge</h2><br/>
        It use the deCONZ rest api to make a bridge beetween your zigbee network and Domoticz (Using Conbee or Raspbee)
        <br/><br/>
        <h3>Remark</h3>
        <ul style="list-style-type:square">
            <li>You can use the file API_KEY.py if you have problems to get your API Key or your Websocket Port</li>
            <li>You can find updated files for deCONZ on their github : https://github.com/dresden-elektronik/deconz-rest-plugin</li>
            <li>If you want the plugin works without connexion, use as IP 127.0.0.1 (if deCONZ and domoticz are on same machine)</li>
            <li>If you are running the plugin for the first time, better to enable debug log (Take Debug info Only)</li>
        </ul>
        <h3>Supported Devices</h3>
        <ul style="list-style-type:square">
            <li>https://github.com/dresden-elektronik/deconz-rest-plugin/wiki/Supported-Devices</li>
        </ul>
        <h3>Configuration</h3>
        Gateway configuration
    </description>
    <params>
        <param field="Address" label="deCONZ IP" width="150px" required="true" default="127.0.0.1"/>
        <param field="Port" label="Port" width="150px" required="true" default="80"/>
        <param field="Mode2" label="API KEY" width="75px" required="true" default="1234567890" />
        <param field="Mode3" label="Debug" width="150px">
            <options>
                <option label="None" value="0"  default="true" />
                <option label="Debug info Only" value="2"/>
                <option label="Basic Debugging" value="62"/>
                <option label="Basic+Messages" value="126"/>
                <option label="Connections Only" value="16"/>
                <option label="Connections+Python" value="18"/>
                <option label="Connections+Queue" value="144"/>
                <option label="All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import json,urllib, time
from fonctions import rgb_to_xy, rgb_to_hsl, xy_to_rgb
from fonctions import Count_Type, ProcessAllState, ProcessAllConfig, First_Json, JSON_Repair, get_JSON_payload
from fonctions import ButtonconvertionXCUBE, ButtonconvertionXCUBE_R, ButtonconvertionTradfriRemote, ButtonconvertionGeneric, VibrationSensorConvertion

#Better to use 'localhost' ?
DOMOTICZ_IP = '127.0.0.1'

LIGHTLOG = True #To disable some activation, log will be lighter, but less informations.
SETTODEFAULT = False #To set device in default state after a rejoin

#https://github.com/febalci/DomoticzEarthquake/blob/master/plugin.py
#https://stackoverflow.com/questions/32436864/raw-post-request-with-json-in-body

class BasePlugin:

    #enabled = False

    def __init__(self):
        self.Devices = {} # id, type, banned , model
        self.NeedToReset = []
        self.Ready = False
        self.Buffer_Command = []
        self.Buffer_Time = ''
        self.Request = None
        self.WebSocket = None
        self.Banned_Devices = []
        self.BufferReceive = ''
        self.BufferLenght = 0

        self.INIT_STEP = ['config','lights','sensors','groups']

        return

    def onStart(self):
        Domoticz.Debug("onStart called")
        #CreateDevice('1111','sensors','On/Off light')

        #Check Domoticz IP
        if Parameters["Address"] != '127.0.0.1' and Parameters["Address"] != 'localhost':
            global DOMOTICZ_IP
            DOMOTICZ_IP = get_ip()
            Domoticz.Log("Your haven't use 127.0.0.1 as IP, so I suppose deCONZ and Domoticz aren't on same machine")
            Domoticz.Log("Taking " + DOMOTICZ_IP + " as Domoticz IP")

            if DOMOTICZ_IP == Parameters["Address"]:
                Domoticz.Status("Your have same IP for deCONZ and Domoticz why don't use 127.0.0.1 as IP")
        else:
            Domoticz.Log("Domoticz and deCONZ are on same machine")

        if Parameters["Mode3"] != "0":
            Domoticz.Debugging(int(Parameters["Mode3"]))
            #DumpConfigToLog()

        #Read banned devices
        with open(Parameters["HomeFolder"]+"banned_devices.txt", 'r') as myPluginConfFile:
            for line in myPluginConfFile:
                if not line.startswith('#'):
                    self.Banned_Devices.append(line.strip())
        myPluginConfFile.close()

        #Read and Set config
        #json = '{"websocketnotifyall":true}'
        #url = '/api/' + Parameters["Mode2"] + '/config/'
        #self.SendCommand(url,json)

        # Disabled, not working for selector ...
        #check for new icons
        #if 'bulbs_group' not in Images:
        #    try:
        #        Domoticz.Image('icons/bulbs_group.zip').Create()
        #    except:
        #        Domoticz.Error("Can't create new icons")

    def onStop(self):
        Domoticz.Debug("onStop called")
        if self.WebSocket:
            self.WebSocket.Disconnect()

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called")

        if Connection.Name == 'deCONZ_WebSocket':

            if (Status != 0):
                Domoticz.Error("WebSocket connexion error : " + str(Connection))
                Domoticz.Error("Status : " + str(Status) + " Description : " + str(Description) )
                return

            Domoticz.Status("Launching websocket on port " + str(Connection.Port) )
            #Need to Add Sec-Websocket-Protocol : domoticz ????
            #Boring error > Socket Shutdown Error: 9, Bad file descriptor
            wsHeader = "GET / HTTP/1.1\r\n" \
                        "Host: "+ Parameters["Address"] + ':' + str(Connection.Port) + "\r\n" \
                        "User-Agent: Domoticz/1.0\r\n" \
                        "Sec-WebSocket-Version: 13\r\n" \
                        "Origin: http://" + DOMOTICZ_IP + "\r\n" \
                        "Sec-WebSocket-Key: qqMLBxyyjz9Tog1bll7K6A==\r\n" \
                        "Connection: keep-alive, Upgrade\r\n" \
                        "Upgrade: websocket\r\n\r\n"
                        #"Accept: Content-Type: text/html; charset=UTF-8\r\n" \
                        #"Pragma: no-cache\r\n" \
                        #"Cache-Control: no-cache\r\n" \
                        #"Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n" \
            self.WebSocket.Send(wsHeader)

        elif Connection.Name == 'deCONZ_Com':

            if (Status != 0):
                Domoticz.Error("deCONZ connexion error : " + str(Connection))
                Domoticz.Error("Status : " + str(Status) + " Description : " + str(Description) )
                return

            if len(self.Buffer_Command) > 0:
                c = self.Buffer_Command.pop(0)
                #Domoticz.Log("### Send" + str(c))
                self.Request.Send(c)
            else:
                self.Request.Disconnect()

        else:
            Domoticz.Error("Unknow connexion : " + str(Connection))
            Domoticz.Error("Status : " + str(Status) + " Description : " + str(Description) )
            return

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")

        _Data = []

        #Domoticz.Log("Data : " + str(Data))
        #Domoticz.Log("Connexion : " + str(Connection))
        #Domoticz.Log("Byte needed : " + str(Connection.BytesTransferred()) +  "ATM : " + str(len(Data)))
        #The max is 4096 so if the data size excess 4096 byte it will be cut

        #Websocket data ?
        if (Connection.Name == 'deCONZ_WebSocket'):
            if Data.startswith(b'\x81'):
                while len(Data) > 0:
                    try:
                        payload, extra_data = get_JSON_payload(Data)
                    except:
                        Domoticz.Error("Malformed JSON response, can't repair : " + str(Data) )
                        return
                    _Data.append(payload)
                    Data = extra_data

                for js in _Data:
                    self.WebSocketConnexion(js)
            else:
                Domoticz.Debug("Websocket Handshake : " + str(Data.decode("utf-8", "ignore").replace('\n','***')) )

        #Normal connexion
        elif Connection.Name == 'deCONZ_Com':
            _DataTmp = ''
            #New frame
            if Data.startswith(b'HTTP'):
                self.BufferLenght = len(Data)
                self.BufferReceive = ''
                Data = Data.decode("utf-8", "ignore")
                _DataTmp = Data.split('\r\n\r\n', 1)[1]

            else:
                self.BufferLenght += len(Data)
                _DataTmp = Data.decode("utf-8", "ignore")

            self.BufferReceive = self.BufferReceive + _DataTmp

            #Frame is completed ?
            l = Connection.BytesTransferred() - self.BufferLenght
            if l > 0:
                #Not complete frame
                Domoticz.Debug("Incomplete trame, miss " + str(l) + " bytes" )
                return

            _Data = self.BufferReceive

            #If not data usefull
            if len(_Data) == 0:
                self.Request.Disconnect()
                return

            #Clean data
            #_Data = _Data.replace('true','True').replace('false','False').replace('null','None').replace('\n','***').replace('\00','')
            try:
                _Data = json.loads(_Data)
            except:
                #Sometime the connexion bug, trying to repair
                Domoticz.Error("Malformed JSON response, Trying to repair : " + str(_Data) )
                _Data = JSON_Repair(_Data)
                try:
                    _Data = json.loads(_Data)
                    Domoticz.Error("New Data repaired : " + str(_Data))
                except:
                    Domoticz.Error("Can't repair malformed JSON: " + str(_Data) )
                    _Data = None

            #Completed frame, force disconnexion
            self.Request.Disconnect()

            #traitement
            if not _Data == None: #WARNING None because can be {}
                self.NormalConnexion(_Data)

            #Next command ?
            self.UpdateBuffer()

        else:
            Domoticz.Log("Unknow Connection" + str(Connection))
            Domoticz.Log("Data : " + str(Data))
            return

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level) + ", Hue: " + str(Hue))

        if not self.Ready == True:
            Domoticz.Error("deCONZ not ready")
            return

        _type,deCONZ_ID = self.GetDevicedeCONZ(Devices[Unit].DeviceID)

        if not deCONZ_ID:
            Domoticz.Error("Device not ready : " + str(Unit) )

        if _type == 'sensors':
            Domoticz.Error("This device don't support action")
            return

        _json = {}

        #on/off
        if Command == 'On':
            _json['on'] = True
            if Level:
                _json['bri'] = round(Level*254/100)
        if Command == 'Off':
            _json['on'] = False

        #level
        if Command == 'Set Level':
            #To prevent bug
            _json['on'] = True

            _json['bri'] = round(Level*254/100)

            #thermostat situation
            if _type == 'config':
                _json.clear()
                _json['mode'] = "auto"
                _json['heatsetpoint'] = Level

        #color
        if Command == 'Set Color':

            #To prevent bug
            _json['on'] = True

            Hue_List = json.loads(Hue)

            #ColorModeNone = 0   // Illegal
            #ColorModeNone = 1   // White. Valid fields: none
            if Hue_List['m'] == 1:
                ww = int(Hue_List['ww']) # Can be used as level for monochrome white
                #TODO : Jamais vu un device avec ca encore
                Domoticz.Debug("Not implemented device color 1")
            #ColorModeTemp = 2   // White with color temperature. Valid fields: t
            if Hue_List['m'] == 2:
                #Value is in mireds (not kelvin)
                #Correct values are from 153 (6500K) up to 588 (1700K)
                # t is 0 > 255
                TempKelvin = int(((255 - int(Hue_List['t']))*(6500-1700)/255)+1700);
                TempMired = 1000000 // TempKelvin
                #if previous not working
                #TempMired = round(float(Hue_List['t'])*(500.0f - 153.0f) / 255.0f + 153.0f)
                _json['ct'] = TempMired
            #ColorModeRGB = 3    // Color. Valid fields: r, g, b.
            elif Hue_List['m'] == 3:
                IEEE = Devices[Unit].DeviceID
                if self.Devices[IEEE].get('colormode','Unknow') == 'hs':
                    h,l,s = rgb_to_hsl((int(Hue_List['r']),int(Hue_List['g']),int(Hue_List['b'])))
                    hue = int(h * 65535)
                    saturation = int(s * 254)
                    value = int(l * 254/100)
                    _json['hue'] = hue
                    _json['sat'] = saturation
                    _json['bri'] = value
                    _json['transitiontime'] = 0
                else:
                    x, y = rgb_to_xy((int(Hue_List['r']),int(Hue_List['g']),int(Hue_List['b'])))
                    x = round(x,6)
                    y = round(y,6)
                    _json['xy'] = [x,y]
            #ColorModeCustom = 4, // Custom (color + white). Valid fields: r, g, b, cw, ww, depending on device capabilities
            elif Hue_List['m'] == 4:
                ww = int(Hue_List['ww'])
                cw = int(Hue_List['cw'])
                x, y = rgb_to_xy((int(Hue_List['r']),int(Hue_List['g']),int(Hue_List['b'])))
                #TODO, Pas trouve de device avec ca encore ...
                Domoticz.Debug("Not implemented device color 2")

            #To prevent bug
            if '"bri":' not in _json:
                _json['bri'] = round(Level*254/100)
                _json['transitiontime'] = 0


        url = '/api/' + Parameters["Mode2"] + '/' + _type + '/' + str(deCONZ_ID)
        if _type == 'lights':
            url = url + '/state'
        elif _type == 'config':
            url = url + '/config'
        elif _type == 'scenes':
            url = '/api/' + Parameters["Mode2"] + '/groups/' + deCONZ_ID.split('/')[0] + '/scenes/' + deCONZ_ID.split('/')[1] + '/recall'
            _json = {} # to force PUT
        else:
            url = url + '/action'

        self.SendCommand(url,json.dumps(_json))

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called for " + str(Connection.Name) )
        if Connection.Name == 'deCONZ_Com':
            self.Request = None
            self.UpdateBuffer()
        else:
            Domoticz.Status("onDisconnect called for " + str(Connection) )

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat called")

        #Initialisation
        if self.Ready != True:
            if len(self.INIT_STEP) > 0:
                Domoticz.Debug("### Initialisation > " + str(self.INIT_STEP[0]))
                self.ManageInit()

                #Stop all here
                return
            else:
               self.Ready = True

        #Check websocket connexion
        if self.WebSocket:
            if not self.WebSocket.Connected():
                Domoticz.Error("WebSocket Disconnected, reconnexion !")
                self.WebSocket.Connect()

        #Check for freeze
        if len(self.Buffer_Command) > 0:
            self.UpdateBuffer()

        #reset switchs
        if len(self.NeedToReset) > 0 :
            for IEEE in self.NeedToReset:
                _id = False
                for i in self.Devices:
                    if i == IEEE:
                        _id = self.Devices[i]['id']
                UpdateDevice(_id,'sensors', { 'nValue' : 0 , 'sValue' : 'Off' } )
            self.NeedToReset = []

        #Devices[27].Update(nValue=0, sValue='11;22' )

    def onDeviceRemoved(self,unit):
        Domoticz.Log("Device Removed")
        #TODO : Need to rescan all

#---------------------------------------------------------------------------------------

    def ManageInit(self,pop = False):
        if pop:
            self.INIT_STEP.pop(0)
        if len(self.INIT_STEP) < 1:
            self.Ready = True

            Domoticz.Status("### deCONZ ready")
            l,s,g,b,o = Count_Type(self.Devices)
            Domoticz.Status("### Found " + str(l) + " Operators, " + str(s) + " Sensors, " + str(g) + " Groups and " + str(o) + " others, with " + str(b) + " Ignored")

            # Compare devices bases
            for i in Devices:
                if Devices[i].DeviceID not in self.Devices:
                    Domoticz.Status('### Device ' + Devices[i].DeviceID + '(' + Devices[i].Name + ') Not in deCONZ ATM, the device is deleted or not ready.')

            return

        Domoticz.Log("### Request " + self.INIT_STEP[0])
        self.SendCommand("/api/" + Parameters["Mode2"] + "/" + self.INIT_STEP[0] + "/")

    def InitDeconz(self,_Data,First_item):
        #Read all devices

        if First_item:
            #Lights or sensors ?
            if 'uniqueid' in _Data[First_item]:
                for i in _Data:

                    IEEE = str(_Data[i]['uniqueid'])
                    Name = str(_Data[i]['name'])
                    Type = str(_Data[i]['type'])
                    Model = str(_Data[i].get('modelid',''))
                    if not Model:
                        Model = ''

                    #Type_device = 'lights'
                    #if not 'hascolor' in _Data[i]:
                    #    Type_device = 'sensors'
                    Type_device = self.INIT_STEP[0]

                    Domoticz.Log("### Device > " + str(i) + ' Name:' + Name + ' Type:' + Type + ' Details:' + str(_Data[i]['state']))

                    self.Devices[IEEE] = {'id' : i , 'type' : Type_device , 'model' : Type}

                    #Skip banned device
                    if IEEE in self.Banned_Devices:
                        Domoticz.Log("Skipping Device (Banned) : " + str(IEEE) )
                        self.Devices[IEEE]['Banned'] = True
                        continue

                    #Get some infos
                    kwarg = {}
                    if 'state' in _Data[i]:
                        state = _Data[i]['state']
                        kwarg.update(ProcessAllState(state,Model))
                        if 'colormode' in state:
                            self.Devices[IEEE]['colormode'] = state['colormode']

                    if 'config' in _Data[i]:
                        config = _Data[i]['config']
                        kwarg.update(ProcessAllConfig(config))

                    #It's a switch ? Need special process
                    if Type == 'ZHASwitch' or Type == 'ZGPSwitch' or Type == 'CLIPSwitch':

                        #Set it to off
                        kwarg.update({'sValue': 'Off', 'nValue': 0})

                        #ignore ZHASwitch if vibration sensor
                        if 'sensitivity' in _Data[i]['config']:
                            continue

                        if 'lumi.sensor_cube' in Model:
                            if IEEE.endswith('-03-000c'):
                                Type = 'XCube_R'
                            elif IEEE.endswith('-02-0012'):
                                Type = 'XCube_C'
                            else:
                                # Useless device
                                self.Devices[IEEE]['Banned'] = True
                                continue
                        elif 'TRADFRI remote control' in Model:
                            Type = 'Tradfri_remote'
                        else:
                            Type = 'Switch_Generic'

                        self.Devices[IEEE]['model'] = Type

                    #Special device
                    if Type == 'ZHAPressure':#ZHAThermostat
                        self.Devices[IEEE + "_heatsetpoint"] = {'id' : i , 'type' : 'config'}

                    #Not exist > create
                    if GetDomoDeviceInfo(IEEE) == False:
                        if Type == 'ZHAThermostat':
                            CreateDevice(IEEE,Name,'ZHATemperature') #Temperature device
                            CreateDevice(IEEE + "_heatsetpoint" ,Name,'ZHAThermostat') #Setpoint device
                        else:
                            CreateDevice(IEEE,Name,Type)

                    #update
                    if kwarg:
                        UpdateDevice(i,Type_device,kwarg)

            #groups
            else:
                for i in _Data:
                    Name = str(_Data[i]['name'])
                    Type = str(_Data[i]['type'])
                    Domoticz.Log("### Groupe > " + str(i) + ' Name:' + Name )
                    Dev_name = 'GROUP_' + Name.replace(' ','_')
                    self.Devices[Dev_name] = {'id' : i , 'type' : 'groups' , 'model' : 'groups'}

                    #Create it in domoticz if not exist
                    if Dev_name in self.Banned_Devices:
                        Domoticz.Log("Skipping Group (Banned) : " + str(Dev_name) )
                        self.Devices[Dev_name]['Banned'] = True

                    #Check for scene
                    scenes = _Data[i].get('scenes',[])
                    if len(scenes) > 0:
                        for j in scenes:
                            Domoticz.Log("### Scenes associated with group " + str(i) + " > ID:" + str(j['id']) + " Name:" + str(j['name']) )
                            Scene_name = 'SCENE_' + str(j['name']).replace(' ','_')
                            self.Devices[Scene_name] = {'id' : str(i) + '/' + str(j['id']) , 'type' : 'scenes' , 'model' : 'scenes'}
                            #Not exist > create
                            if GetDomoDeviceInfo(Scene_name) == False:
                                CreateDevice(Scene_name,str(j['name']),'Scenes')

                    else:
                        #Not exist > create
                        if GetDomoDeviceInfo(Dev_name) == False:
                            CreateDevice(Dev_name,Name,Type)

        #Update initialisation
        self.ManageInit(True)

    def NormalConnexion(self,_Data):

        Domoticz.Debug("Classic Data : " + str(_Data) )

        #JSON with data returned >> _Data = [{'success': {'/lights/2/state/on': True}}, {'success': {'/lights/2/state/bri': 251}}]
        if isinstance(_Data, list):
            self.ReadReturn(_Data)
        else:

            try:
                First_item = next(iter(_Data))
            except:
                #Special case, if the user don't have this kind of device >> _Data = {}
                if (self.Ready != True) and ( len(_Data) == 0) :
                    self.InitDeconz(_Data,None)
                else:
                    Domoticz.Error("Bad JSON response (or empty): " + str(_Data) )
                return

            # JSON with device list >  {'1': {'data:1}}
            if isinstance(First_item, str):
                if First_item.isnumeric():
                    self.InitDeconz(_Data,First_item)
                elif 'websocketnotifyall' in _Data:
                    self.ReadConfig(_Data)
                else:
                    Domoticz.Error("Not managed JSON : " + str(_Data) )

    def ReadReturn(self,_Data):
        kwarg = {}
        _id = False
        _type = False

        for _Data2 in _Data:

            First_item = next(iter(_Data2))

            #Command Error
            if First_item == 'error':
                Domoticz.Error("deCONZ error :" + str(_Data2))
                if _Data2['error']['type'] == 3:
                    dev = _Data2['error']['address'].split('/')
                    _id = dev[2]
                    _type = dev[1]
                    #Set red header
                    kwarg.update({'TimedOut':1})

            #Command sucess
            elif First_item == 'success':

                data = _Data2['success']
                dev = (list(data.keys())[0] ).split('/')
                val = data[list(data.keys())[0]]

                if len(dev) < 3:
                    pass
                else:
                    if not _id:
                        _id = dev[2]
                        _type = dev[1]

                    if dev[1] == 'config':
                        Domoticz.Status("Editing configuration : " + str(data) )

            else:
                Domoticz.Error("Not managed return JSON : " + str(_Data2) )

        if kwarg:
            UpdateDevice(_id,_type,kwarg)

    def ReadConfig(self,_Data):
        Domoticz.Status("Firmware version : " + _Data['fwversion'] )
        Domoticz.Status("Websocketnotifyall : " + str(_Data['websocketnotifyall']))
        if not _Data['websocketnotifyall'] == True:
            Domoticz.Error("Websocketnotifyall is not set to True")

        #Launch Web socket connexion
        self.WebSocket = Domoticz.Connection(Name="deCONZ_WebSocket", Transport="TCP/IP", Address=Parameters["Address"], Port=str(_Data['websocketport']) )
        self.WebSocket.Connect()

        self.ManageInit(True)

    def WebSocketConnexion(self,_Data):

        Domoticz.Debug("###### WebSocket Data : " + str(_Data) )

        if not self.Ready == True:
            Domoticz.Error("deCONZ not ready")
            return

        if 'e' in _Data:
            if _Data['e'] == 'deleted':
                return
            if _Data['e'] == 'added':
                return
            if _Data['e'] == 'scene-called':
                Domoticz.Log("Playing scene > group:" + str(_Data['gid']) + " Scene:" + str(_Data['scid']) )
                return

        #Take care, no uniqueid for groups
        IEEE = str(_Data.get('uniqueid',self.GetDeviceIEEE(_Data['id'],_Data['r'])))
        if IEEE == 'banned':
            Domoticz.Debug("Banned device > " + str(_Data['id']) + ' (' + str(_Data['r']) + ')')
            return
        if not IEEE or (IEEE not in self.Devices):
            Domoticz.Error("Websocket error, unknow device > " + str(_Data['id']) + ' (' + str(_Data['r']) + ')')
            #Try getting informations
            #self.SendCommand('/api/' + Parameters["Mode2"] + '/' + str(_Data['r']) + '/' + str(_Data['id']) )
            return
        model = self.Devices[IEEE].get('model','')

        kwarg = {}

        #MAJ State : _Data['e'] == 'changed'
        if 'state' in _Data:
            state = _Data['state']
            kwarg.update(ProcessAllState(state , model))

            if 'buttonevent' in state:
                if model == 'XCube_C':
                    kwarg.update(ButtonconvertionXCUBE( state['buttonevent'] ) )
                elif model == 'XCube_R':
                    kwarg.update(ButtonconvertionXCUBE_R( state['buttonevent'] ) )
                elif model == 'Tradfri_remote':
                    kwarg.update(ButtonconvertionTradfriRemote( state['buttonevent'] ) )
                else:
                    kwarg.update(ButtonconvertionGeneric( state['buttonevent'] ) )
                if IEEE not in self.NeedToReset:
                    self.NeedToReset.append(IEEE)

            if 'vibration' in state:
                kwarg.update(VibrationSensorConvertion( state['vibration'] , state.get('tiltangle',None)) )

            if 'reachable' in state:
                if state['reachable'] == True:
                    Unit = GetDomoDeviceInfo(IEEE)
                    LUpdate = Devices[Unit].LastUpdate
                    LUpdate=time.mktime(time.strptime(LUpdate,"%Y-%m-%d %H:%M:%S"))
                    current = time.time()

                    if (SETTODEFAULT):
                        #Check if the device has been see, at least 10 s ago
                        if (current-LUpdate) > 10:
                            Domoticz.Status("###### Device just re-connected : " + str(_Data) + "Set to defaut state")
                            self.SetDeviceDefautState(IEEE,_Data['r'])
                        else:
                            Domoticz.Status("###### Device just re-connected : " + str(_Data) + "But ignored")

            if ('tampered' in state) or ('lowbattery' in state):
                tampered = state.get('tampered',False)
                lowbattery = state.get('lowbattery',False)
                if tampered or lowbattery:
                    kwarg.update({'TimedOut':1})
                    Domoticz.Error("###### Device with hardware defaut : " + str(_Data))


        #MAJ config
        elif 'config' in _Data:
            config = _Data['config']
            kwarg.update(ProcessAllConfig(config))

        else:
            Domoticz.Error("Unknow MAJ" + str(_Data) )

        if kwarg:
            UpdateDevice(_Data['id'],_Data['r'],kwarg)

    def DeleteDeviceFromdeCONZ(self,_id):
        url = '/api/' + Parameters["Mode2"] + '/sensors/' + str(_id)

        sendData = "DELETE " + url + " HTTP/1.1\r\n" \
                    "Host: " + Parameters["Address"] + ':' + Parameters["Port"] + "\r\n" \
                    "Connection: keep-alive\r\n\r\n"

        self.Buffer_Command.append(sendData)
        self.UpdateBuffer()

        Domoticz.Status("### Deleting device " + str(_id))

    def SendCommand(self,url,data=None):

        Domoticz.Debug("Send Command " + url + " with " + str(data) + ' (' + str(len(self.Buffer_Command)) + ' in buffer)')

        if data == None:
            sendData = "GET " + url + " HTTP/1.1\r\n" \
                        "Host: " + Parameters["Address"] + ':' + Parameters["Port"] + "\r\n" \
                        "User-Agent: Domoticz/1.0\r\n" \
                        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n" \
                        "Connection: keep-alive\r\n\r\n"
        else:
            sendData = "PUT " + url + " HTTP/1.1\r\n" \
                        "Host: " + Parameters["Address"] + ':' + Parameters["Port"] + "\r\n" \
                        "User-Agent: Domoticz/1.0\r\n" \
                        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n" \
                        "Content-Type: application/x-www-form-urlencoded\r\n" \
                        "Content-Length: " + str(len(data)) + "\r\n" \
                        "Connection: keep-alive\r\n\r\n"
            sendData = sendData + data + "\r\n"

        self.Buffer_Command.append(sendData)
        self.UpdateBuffer()

    def GetDevicedeCONZ(self,IEEE):
        for i in self.Devices:
            if i == IEEE:
                return self.Devices[IEEE]['type'],self.Devices[IEEE]['id']

        return False,False

    def UpdateBuffer(self):
        if len(self.Buffer_Command) == 0:
            return

        if self.Request == None: # or not (self.Request.Connecting() or self.Request.Connected())):
            Domoticz.Debug("Autorising connection")
            self.Request = Domoticz.Connection(Name="deCONZ_Com", Transport="TCP/IP", Address=Parameters["Address"] , Port=Parameters["Port"])
            self.Request.Connect()
            self.Buffer_Time = time.time()
        else:
            #Ok, we can't send new command, check if the system is freezed
            if (time.time() - self.Buffer_Time) > 5:
                Domoticz.Error("More than 5s timeout, Your system seem frezzed, Forcing disconnect for : " + str(self.Buffer_Command[0]))
                self.Request.Disconnect()

    def GetDeviceIEEE(self,_id,_type):
        for IEEE in self.Devices:
            #Domoticz.Log("#################" + str(IEEE) + ' ' + str( self.Devices[IEEE]['id']) + ' ' + str(self.Devices[IEEE]['type'] ) )
            if (self.Devices[IEEE]['type'] == _type) and (self.Devices[IEEE]['id'] == _id):
                if self.Devices[IEEE].get('Banned',False) == True:
                    return 'banned'
                return IEEE

        return False

    def SetDeviceDefautState(self,IEEE,_type):
        # Set bulb on same state than in domoticz
        if _type == 'lights':
            Unit = GetDomoDeviceInfo(IEEE)
            if Devices[Unit].nValue == 0:
                _json = '{"on":false}'
            else:
                _json = '{"on":true}'
            dummy,deCONZ_ID = self.GetDevicedeCONZ(IEEE)
            url = '/api/' + Parameters["Mode2"] + '/lights/' + str(deCONZ_ID) + '/state'
            self.SendCommand(url,_json)

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def onDeviceRemoved(unit):
    global _plugin
    _plugin.onDeviceRemoved(unit)

    # Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

def GetDeviceIEEE(id,type):
    global _plugin
    return _plugin.GetDeviceIEEE(id,type)

#*****************************************************************************************************

def get_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def GetDomoDeviceInfo(IEEE):
    for x in Devices:
        if Devices[x].DeviceID == str(IEEE) :
            return x
    return False

def FreeUnit() :
    FreeUnit = ""
    for x in range(1,256):
        if x not in Devices :
            FreeUnit=x
            return FreeUnit
    if FreeUnit == "" :
        FreeUnit=len(Devices)+1
    return FreeUnit

def GetDomoUnit(_id,_type):
    try:
        IEEE = GetDeviceIEEE(_id,_type)

        if IEEE == 'banned':
            Domoticz.Log("Banned device > " + str(_id) + ' (' + str(_type) + ')')
            return 'banned'
        elif IEEE == False:
            Domoticz.Log("Device not in base, need resynchronisation ? > " + str(_id) + ' (' + str(_type) + ')')
            return False

        return GetDomoDeviceInfo(IEEE)
    except:
        return False

    return False

def UpdateDevice(_id,_type,kwarg):

    Unit = GetDomoUnit(_id,_type)

    if Unit == 'banned':
        return

    if not Unit or not kwarg:
        Domoticz.Error("Can't Update Unit > " + str(_id) + ' (' + str(_type) + ')' )
        return

    #Check for special device.
    if 'heatsetpoint' in kwarg:
        v = kwarg.pop('heatsetpoint')
        IEEE = GetDeviceIEEE(_id,_type)
        Unit = GetDomoDeviceInfo(IEEE + '_heatsetpoint')
        kwarg['nValue'] = 0
        kwarg['nValue'] = str(v)

    #Do we need to update the sensor ?
    NeedUpdate = False

    for a in kwarg:
        if kwarg[a] != getattr(Devices[Unit], a ):
            NeedUpdate = True
            break

    #Force update even there is no change, for exemple in case the user press a switch too fast, to not miss an event
    # Only for switch > 'LevelNames' in Devices[Unit].Options
    # Only sensors >  _type == 'sensors'
    if (('nValue' in kwarg) or ('sValue' in kwarg)) and ( ('LevelNames' in Devices[Unit].Options) and (kwarg['nValue'] != 0) ):
        NeedUpdate = True

    #Disabled because no update for battery or last seen for exemple
    #No need to trigger in this situation
    #if (kwarg['nValue'] == Devices[Unit].nValue) and (kwarg['nValue'] == Devices[Unit].nValue) and ('Color' not in kwarg):
    #    kwarg['SuppressTriggers'] = True

    #Alaways update for Color Bulb
    if 'Color' in kwarg:
        NeedUpdate = True

    #force update, at least 1 every 24h
    if not NeedUpdate:
        LUpdate = Devices[Unit].LastUpdate
        LUpdate=time.mktime(time.strptime(LUpdate,"%Y-%m-%d %H:%M:%S"))
        current = time.time()
        if (current-LUpdate) > 86400:
            NeedUpdate = True

    #Theses value are needed for Domoticz
    if 'nValue' not in kwarg:
        kwarg['nValue'] = Devices[Unit].nValue
    if 'sValue' not in kwarg:
        kwarg['sValue'] = Devices[Unit].sValue
    if Devices[Unit].TimedOut != 0 and kwarg.get('TimedOut',0) == 0:
        NeedUpdate = True
        kwarg['TimedOut'] = 0

    if NeedUpdate or not LIGHTLOG:
        Domoticz.Debug("### Update  device ("+Devices[Unit].Name+") : " + str(kwarg))
        Devices[Unit].Update(**kwarg)
    else:
        Domoticz.Debug("### Update  device ("+Devices[Unit].Name+") : " + str(kwarg) + ", IGNORED , no changes !")

def CreateDevice(IEEE,_Name,_Type):
    kwarg = {}
    Unit = FreeUnit()
    TypeName = ''

    #Operator
    if _Type == 'Color light' or _Type == 'Color dimmable light':
        kwarg['Type'] = 241
        kwarg['Subtype'] = 2
        kwarg['Switchtype'] = 7

    elif _Type == 'Extended color light':
        kwarg['Type'] = 241
        kwarg['Subtype'] = 7
        kwarg['Switchtype'] = 7

    elif _Type == 'Color temperature light':
        kwarg['Type'] = 241
        kwarg['Subtype'] = 8
        kwarg['Switchtype'] = 7

    elif _Type == 'Dimmable light' or _Type == 'Dimmable plug-in unit' or _Type == 'Dimmer switch':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 73
        kwarg['Switchtype'] = 7

    elif _Type == 'Smart plug' or _Type == 'On/Off plug-in unit':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 73
        kwarg['Switchtype'] = 0
        kwarg['Image'] = 1

    elif _Type == 'On/Off light' or _Type == 'On/Off output' or _Type == 'On/Off light switch':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 73
        kwarg['Switchtype'] = 0

    elif _Type == 'Window covering device':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 73
        kwarg['Switchtype'] = 16

    elif _Type == 'Door Lock':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 73
        kwarg['Switchtype'] = 0

    #elif _Type == 'Fan':

    #Sensors
    elif _Type == 'Daylight':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 73
        kwarg['Switchtype'] = 9

    elif _Type == 'ZHATemperature' or _Type == 'CLIPTemperature':
        kwarg['TypeName'] = 'Temperature'

    elif _Type == 'ZHAHumidity' or _Type == 'CLIPHumidity':
        kwarg['TypeName'] = 'Humidity'

    elif _Type == 'ZHAPressure'or _Type == 'CLIPPressure':
        kwarg['TypeName'] = 'Barometer'

    elif _Type == 'ZHAOpenClose' or _Type == 'CLIPOpenClose':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 73
        kwarg['Switchtype'] = 11

    elif _Type == 'ZHAPresence' or _Type == 'CLIPPresence':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 73
        kwarg['Switchtype'] = 8

    elif _Type == 'ZHALightLevel' or _Type == 'CLIPLightLevel':
        kwarg['TypeName'] = 'Illumination'

    elif _Type == 'ZHAConsumption':# in kWh
        kwarg['TypeName'] = 'kWh'

    elif _Type == 'ZHAPower':# in W
        kwarg['TypeName'] = 'Usage'

    elif _Type == 'ZHAVibration':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 62
        kwarg['Switchtype'] = 18
        kwarg['Options'] = {"LevelActions": "|||", "LevelNames": "Off|Vibrate|Rotation|drop", "LevelOffHidden": "true", "SelectorStyle": "0"}

    elif _Type == 'ZHAThermostat' or _Type == 'CLIPThermostat':
        kwarg['Type'] = 242
        kwarg['Subtype'] = 1

    elif _Type == 'ZHAAlarm':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 73
        kwarg['Switchtype'] = 2

    elif _Type == 'ZHAWater':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 62
        kwarg['Switchtype'] = 5
        kwarg['Image'] = 11 # Visible only on floorplan

    elif _Type == 'ZHAFire' or _Type == 'ZHACarbonMonoxide':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 62
        kwarg['Switchtype'] = 5

    elif _Type == 'CLIPGenericStatus':
        kwarg['TypeName'] = 'Text'

    elif _Type == 'CLIPGenericFlag':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 62
        kwarg['Switchtype'] = 2

    #Switch
    elif _Type == 'Switch_Generic':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 62
        kwarg['Switchtype'] = 18
        kwarg['Image'] = 9
        kwarg['Options'] = {"LevelActions": "||||||", "LevelNames": "Off|B1|B2|B3|B4|B5|B6|B7|B8", "LevelOffHidden": "true", "SelectorStyle": "0"}

    elif _Type == 'Tradfri_remote':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 62
        kwarg['Switchtype'] = 18
        kwarg['Image'] = 9
        kwarg['Options'] = {"LevelActions": "|||||", "LevelNames": "Off|On|More|Less|Right|Left", "LevelOffHidden": "true", "SelectorStyle": "0"}

    elif _Type == 'XCube_C':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 62
        kwarg['Switchtype'] = 18
        kwarg['Image'] = 9
        kwarg['Options'] = {"LevelActions": "||||||||", "LevelNames": "Off|Shak|Wake|Drop|90°|180°|Push|Tap", "LevelOffHidden": "true", "SelectorStyle": "0"}

    elif _Type == 'XCube_R':
        kwarg['TypeName'] = 'Custom'
        kwarg['Options'] = {"Custom": ("1;degree")}

    #groups
    elif _Type == 'LightGroup' or _Type == 'groups':
        kwarg['Type'] = 241
        kwarg['Subtype'] = 7
        kwarg['Switchtype'] = 7
        #if 'bulbs_group' in Images:
        #    kwarg['Image'] = Images['bulbs_group'].ID

    #Scenes
    elif _Type == 'Scenes':
        kwarg['Type'] = 244
        kwarg['Subtype'] = 62
        kwarg['Switchtype'] = 9
        kwarg['Image'] = 9

    else:
        Domoticz.Error("Unknow device type " + _Type )
        return

    kwarg['DeviceID'] = IEEE
    kwarg['Name'] = _Name
    kwarg['Unit'] = Unit
    Domoticz.Device(**kwarg).Create()

    Domoticz.Status("### Create Device " + IEEE + " > " + _Name + ' (' + _Type +') as Unit ' + str(Unit) )
