// requires: msgpack https://github.com/ygoe/msgpack.js/
//                   https://github.com/kawanet/msgpack-lite
//           cash https://github.com/fabiospampinato/cash
//
'use strict';

var DeFramed = function(){
	this.has_error = false;

	this._setupListeners();
	this._setupWebsocket();
};

DeFramed.prototype._setupListeners = function(){
	var self = this;

	document.addEventListener('DOMContentLoaded', function() {
		self._augmentInterface();
	});
	document.addEventListener('DOMSubtreeModified', function() {
		self._augmentInterface();
	});
	window.onbeforeunload = function(){
		self.ws && self.ws.close();
	};
};

DeFramed.prototype._setupWebsocket = function(){
	var socketUrl = window.location.protocol.replace('http', 'ws') + '//' + window.location.host + '/websocket';
	this.ws = new WebSocket(socketUrl);
	var self = this;

	this.ws.onclose = function(event){
		if (self.has_error) { return; }
		announce("error","Connection closed. Reloading.");
		setTimeout(function(){
			self.ws.readyState > 1 && self._setupWebsocket();
		}, 1000);
	};

	this.ws.onerror = function (event) {
		announce("error","Connection error. Reloading.");
		setTimeout(function(){
			self.ws.readyState > 1 && self._setupWebsocket();
		}, 1000);
	};

	this.ws.onmessage = function(event){
		var m = msgpack.decode(event.data);
		this['msg_'+m.type](m);
	};

	this.ws.onopen = function (msg) {
		ws.send(msgpack.encode({"type":"login", "token":window.websocket_token}));
		announce("info",'Initializing …');
	};
};

DeFramed.prototype.send = function(req) {
	this.ws.send(msgpack.encode(req));
};

DeFramed.prototype.announce = function(c,m) {
	// Displays some announcement or other
	$("#main_info").remove();
	if (c == "error") {
		has_error = true;
	}
	var li = $('<tr/>');
	li.attr('id', 'info').addClass(c);

	var ld = $('<th/>');
	ld.text(c);
	li.append(ld);

	ld = $('<td/>');
	ld.text(m);
	li.append(ld);
	$('tbody#main_log').prepend(li);
};

DeFramed.prototype.m_auth_ok = function(m) {
	announce("info",'Connected. Requesting data.');
	req = {"type":"start"};
	ws.send(msgpack.encode(req));
};

DeFramed.prototype.m_error = function(m) {
	var d = $("<td/>")
	d.addClass("error");
	if ("display" in m) {
		d.text(m.display);
	} else {
		d.text("Error decoding: "+msg.data);
	}
};

DeFramed.prototype.m_fail = function(m) {
	announce("error","Disconnected: "+m.message);
	this.ws.close();
};

$(function() { window.DF = new DeFramed(); })
