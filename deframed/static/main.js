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

DeFramed.prototype.announce = function(typ,txt,timeout){
	if (txt === undefined) {
		$(`#df_${typ}`).remove();
		return;
	}
	var a = `
		<div id="df_${typ}" class="alert alert-dismissible alert-${typ}" role="alert">
			${txt}
			<button type="button" class="close" data-dismiss="alert" aria-label="Close">
				<span aria-hidden="true">&times;</span>
			</button>
		</div>
	`;
	$(`#df_${typ}`).remove();
	$("#df_alerts").prepend(a);
	if(timeout > 0.1) {
		var fo = function() {
			// $(`#df_${typ}`).fadeOut(1000, function(e) { $(e).remove(); });
			$(`#df_${typ}`).remove();
		};
		setTimeout(fo, timeout*1000);
	}
};

DeFramed.prototype._setupWebsocket = function(){
	var socketUrl = window.location.protocol.replace('http', 'ws') + '//' + window.location.host + '/ws';
	this.ws = new WebSocket(socketUrl);
	this.ws.binaryType = 'arraybuffer';
	this.has_error = false;
	this.backoff = 100;
	var self = this;

	this.ws.onclose = function(event){
		if (self.has_error) { return; }
		self.announce("danger","Connection closed. Retrying soon.");
		if(self.backoff < 30000) { self.backoff = self.backoff * 1.5; }
		setTimeout(function(){
			self.ws.readyState > 1 && self._setupWebsocket();
		}, self.backoff);
	};

	this.ws.onerror = function (event) {
		self.announce("danger","Connection error. Reloading soon.");
		if(self.backoff < 30000) { self.backoff = self.backoff * 1.5; }
		self.has_error = true;
		setTimeout(function(){
			self.ws.readyState > 1 && self._setupWebsocket();
		}, self.backoff);
	};

	this.ws.onmessage = function(event){
		var m = msgpack.decode(event.data);
		var action = m[0];
		m = m[1];
		console.log("IN",action,m);
		var p = self["msg_"+action];
		if (p === undefined) {
			self.announce("warning",`Unknown message type '${action}'`);
		} else {
			try {
				p.call(self,m);
				if (self.backoff < 200) { self.backoff = self.backoff / 2; }
			} catch(e) {
				console.log(e);
				self.announce("warning",`Message '${action}' caused error ${e}`)
			}
		}
	};

	this.ws.onopen = function (msg) {
		$("#df_spinner").show();
		self.announce("danger");
		self.send("first", {"uuid":window.deframed_uuid, "uuid":self.uuid, "token":self.token});
		self.announce("info",'Talking to the server. Stand by.');
	};
};

DeFramed.prototype.send = function(action,data) {
	console.log("OUT",action,data);
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
		console.log("OUT","reply",n,data);
		this.ws.send(msgpack.encode(["reply",[n,data]]));
	} catch(e) {
		console.log("OUT","reply",n,e,data);
		this.ws.send(msgpack.encode(["reply",[n,{"_error":e, "action":action, "n":n, "data":data}]]));
	}
};

DeFramed.prototype.msg_info = function(m) {
	this.announce(m.level, m.text, m.timeout);
	var b = m.busy;
	if(b === undefined) {}
	else if(b) { $("#df_spinner").show(); }
	else { $("#df_spinner").hide(); }
}

DeFramed.prototype.req_ping = function(m) {
	t = this.token;
	this.token = m;
	return t;
}

DeFramed.prototype.msg_ping = function(m) {
	this.token = m;
	this.send("pong",m);
}

DeFramed.prototype.msg_set = function(m) {
	$("#"+m.id).html(m.content);
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
}

DeFramed.prototype.m_auth_ok = function(m) {
	this.announce("info",'Connected. Requesting data.');
	this.send("start",null);
};

DeFramed.prototype.m_error = function(m) {
	var d = $("<td/>")
	d.addClass("danger");
	if ("display" in m) {
		d.text(m.display);
	} else {
		d.text("Error decoding: "+msg.data);
	}
};

DeFramed.prototype.m_fail = function(m) {
	this.announce("danger","Disconnected: "+m.message);
	this.ws.close();
};


DeFramed.prototype._augmentInterface = function(){
	var tags = document.getElementsByTagName('BUTTON');
	for(var i = 0; i < tags.length; i++){
		this._augmentButton(tags.item(i));
	}
	tags = document.getElementsByTagName('FORM');
	for(var i = 0; i < tags.length; i++){
		this._augmentForm(tags.item(i));
	}
};

DeFramed.prototype._augmentButton = function(ele){
	if(!ele.dataset.url){
		return;
	}
	if(ele.onclick){	// already done
		return;
	}
	console.log('augmenting button: ', ele);
	var self = this;
	ele.onclick = function(){
		self.send("button",ele.id);
	}
};

DeFramed.prototype._augmentForm = function(ele){
	if(ele.onsubmit){	// already done
		return;
	}
	console.log('augmenting form: ', ele);
	var self = this;
	ele.onsubmit = function(){
		var res = {"_id":ele.id};
		for(var e of ele.elements) {
			res[e.name] = e.value;
		}
		self.send("submit",ele);
		return false;
	}
};

DeFramed.prototype._elementActivated = function(action,ele){
	console.log('element activated:', ele);
	this.send(action, this._getActionURL(ele));
};

$(function() {
	window.DF = new DeFramed();
	$("#init_alert").remove();

	$("a").attr("draggable",false);
	$(window).on('resize',function(){
		var hh = $('header').height();
		$('main').offset({top:hh, left:0});
		hh = $('body').height()-hh-$('footer').height();
		$('main').height(hh);
	});
	$(window).trigger('resize');
})
