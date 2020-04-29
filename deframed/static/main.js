// requires: msgpack https://github.com/ygoe/msgpack.js/
//                   https://github.com/kawanet/msgpack-lite
//           cash https://github.com/fabiospampinato/cash
//
'use strict';

var DeFramed = function(){
	this.has_error = false;
	this.token = null;

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
		this["msg_"+m[0]](m[1]);
	};

	this.ws.onopen = function (msg) {
		self.send("first", {"uuid":window.deframed_uuid, "token":self.token});
		announce("info",'Initializing …');
	};
};

DeFramed.prototype.send = function(action,data) {
	if(action == "reply") {
		console.log("You can't reply here",data);
	} else {
		this.ws.send(msgpack.encode([action,data]));
	}
};

DeFramed.prototype.msg_req = function(data) {
	action=data[0];
	n=data[1];
	data=data[2];
	try {
		data=this["req_"+action](data);
		this.ws.send(msgpack.encode(["reply",[n,data]]));
	} catch(e) {
		this.ws.send(msgpack.encode(["reply",[n,{"_error":e, "action":action, "n":n, "data":data}]]));
	}
};

DeFramed.prototype.msg_info = function(m) {
	this.announce(m.level, m.text);
}

DeFramed.prototype.req_ping = function(m) {
	t = this.token;
	this.token = m;
	return t;
}

DeFramed.prototype.msg_ping = function(m) {
	t = this.token;
	this.token = m;
	this.send("pong",m);
}

DeFramed.prototype.req_getattr = function(m) {
	res = []

	Object.keys(m).forEach(k => {
		var v = m[k];
		var r = {};
		var e = document.getElementById(k);
		if (e === undefined) {
			res.push(null);
		} else {
			for(var kk of v) {
				r[kk] = e.getAttribute(kk);
			}
		}
		res[k] = r;
	});
	return res;

	this.token = m; this.send("pong",m);
}

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
	this.send("start",null);
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
