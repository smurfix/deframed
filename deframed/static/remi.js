'use strict';

var ws = null;
var comTimeout = null;
var failedConnections = 0;
var webBuf = [];

function openSocket() {
    var ws_wss = "ws";
    try {
        ws_wss = document.location.protocol.startsWith('https')?'wss':'ws';
    } catch(ex) {}
    var host = document.location.host;
    var path = document.location.pathname.replace("/sub/","/ws/");

    try {
        ws = new WebSocket(`${ws_wss}:${host}/${path}`);
        console.debug('Using websocket',ws);
        ws.binaryType = 'arraybuffer';
        ws.onopen = websocketOnOpen;
        ws.onmessage = websocketOnMessage;
        ws.onclose = websocketOnClose;
        ws.onerror = websocketOnError;
    } catch(ex) {
        ws=null;
        alert('websocket not supported or server unreachable');
    }
}
openSocket();

function websocketOnMessage (evt){
    var msg = evt.data;
    msg = msgpack.decode(msg);
    console.log("IN Remi",msg);
    var action = msg[0];
    msg = msg[1];

    if (action == 'show') {
        document.body.innerHTML = decodeURIComponent(msg);

    } else if (action == 'update' ) {
        var focusedElement=-1;
        var caretStart=-1;
        var caretEnd=-1;
        if (document.activeElement) {
            focusedElement = document.activeElement.id;
            try {
                caretStart = document.activeElement.selectionStart;
                caretEnd = document.activeElement.selectionEnd;
            } catch(e) {}
        }
        var idElem = msg[0];
        msg = msg[1];

        var elem = document.getElementById(idElem);
        try {
            elem.insertAdjacentHTML('afterend',decodeURIComponent(msg));
            elem.parentElement.removeChild(elem);
        } catch(e) {
            /*Microsoft EDGE doesn't support insertAdjacentHTML for SVGElement*/
            var ns = document.createElementNS("http://www.w3.org/2000/svg",'tmp');
            ns.innerHTML = decodeURIComponent(msg);
            elem.parentElement.replaceChild(ns.firstChild, elem);
        }

        var elemToFocus = document.getElementById(focusedElement);
        if (elemToFocus != null) {
            elemToFocus.focus();
            try {
                elemToFocus = document.getElementById(focusedElement);
                if(caretStart>-1 && caretEnd>-1)
                    elemToFocus.setSelectionRange(caretStart, caretEnd);
            } catch(e) {}
        }
    } else if (action == 'eval') {
        try {
            eval(msg);
        } catch(e) { console.debug(e.message); };
    } else {
        console.log("Unknown msg",action,msg);
    }
};

var sendCallbackParam = function (widgetID,functionName,params) {
    var message = msgpack.encode(['callback',[widgetID,functionName,params]])
    if (webBuf !== null) {
        console.log("OUT RemiD",widgetID,functionName,params);
        webBuf.push(message)
        return;
    }
    console.log("OUT Remi",widgetID,functionName,params);
    if (ws !== null)
        ws.send(message);
};

var sendCallback = function (widgetID,functionName) {
    sendCallbackParam(widgetID,functionName,{});
};

function renewConnection(){
    // ws.readyState:
    //A value of 0 indicates that the connection has not yet been established.
    //A value of 1 indicates that the connection is established and communication is possible.
    //A value of 2 indicates that the connection is going through the closing handshake.
    //A value of 3 indicates that the connection has been closed or could not be opened.
    if (ws === null) {
        openSocket();
        return;
    }
    if (ws.readyState == 0) return; // just wait for the connection to be stablished
    if (ws.readyState == 1) return;

    openSocket();
};

function websocketOnClose(evt) {
    /* websocket is closed. */
    // Some explanation on this error: http://stackoverflow.com/questions/19304157/getting-the-reason-why-websockets-closed
    // In practice, on a unstable network (wifi with a lot of traffic for example) this error appears
    // Got it with Chrome saying:
    // WebSocket connection to 'ws://x.x.x.x:y/' failed: Could not decode a text frame as UTF-8.
    // WebSocket connection to 'ws://x.x.x.x:y/' failed: Invalid frame header

    if (ws === null)
        return;
    console.debug('Connection is closed:', evt)
    ws = null;
    try {
        document.getElementById("loading").style.display = '';
    } catch(err) {
        console.log('Error hiding loading overlay', err);
    }

    failedConnections += 1;

    console.debug('failed connections', failedConnections)

    if(evt.code == 1006){
        renewConnection();
    }

};

function websocketOnError(evt){
    /* websocket is crashed. */
    if (ws === null)
        return;
    ws = null;
    console.debug('Websocket error', evt);
};

function websocketOnOpen(evt){
    if(ws.readyState == 1){
        console.debug('websocket OK');
        try {
            document.getElementById("loading").style.display = 'none';
        } catch(err) {
            console.log('Error hiding loading overlay ' + err.message);
        }

        failedConnections = 0;
        if (webBuf !== null)
            webBuf.forEach(function(msg) {
                ws.send(msg);
            });
        webBuf = null;
    } else {
        console.debug('onopen fired but the socket readyState was not 1');
    }
};

function uploadFile(widgetID, eventSuccess, eventFail, eventData, file){
    var url = '/';
    var xhr = new XMLHttpRequest();
    var fd = new FormData();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('filename', file.name);
    xhr.setRequestHeader('listener', widgetID);
    xhr.setRequestHeader('listener_function', eventData);
    xhr.onreadystatechange = function() {
        if (xhr.readyState == 4 && xhr.status == 200) {
            /* Every thing ok, file uploaded */
            var params={};params['filename']=file.name;
            sendCallbackParam(widgetID, eventSuccess,params);
            console.log('upload success: ' + file.name);
        }else if(xhr.status == 400){
            var params={};params['filename']=file.name;
            sendCallbackParam(widgetID,eventFail,params);
            console.log('upload failed: ' + file.name);
        }
    };
    fd.append('upload_file', file);
    xhr.send(fd);
};
