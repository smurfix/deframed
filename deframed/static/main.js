// requires: msgpack https://github.com/ygoe/msgpack.js/
//                   https://github.com/kawanet/msgpack-lite
//           cash https://github.com/fabiospampinato/cash
//
'use strict';

var DeFramed = function(){
	this.has_error = false;
	this.token = sessionStorage.getItem('token');
	if (this.token === undefined) this.token = null;
	this.version = null;
	this.backoff = 100;
	this.debug = sessionStorage.getItem('debug');
	this.reconnect_timer = null;

	this._setupListeners();
	this._setupWebsocket();
};

DeFramed.prototype._setupListeners = function(){
	var self = this;

	document.addEventListener('DOMContentLoaded', function() {
		self._augmentInterface();
	});
	if(window.MutationObserver) {
		// Select the node that will be observed for mutations
		const targetNode = document.getElementById('some-id');

		// Options for the observer (which mutations to observe)
		const config = { attributes: true, childList: true, subtree: true };

		// Callback function to execute when mutations are observed
		const callback = function(mutationsList, observer) {
			// Use traditional 'for loops' for IE 11
			// for(let mutation of mutationsList) { do_something; }
			self._augmentInterface();
		};

		// Create an observer instance linked to the callback function
		const observer = new MutationObserver(callback);

		// Start observing the target node for configured mutations
		observer.observe(document, config);
	} else {
		document.addEventListener('DOMSubtreeModified', function() {
			self._augmentInterface();
		});
	}
	window.onbeforeunload = function(){
		if (self.ws) {
			// prevent reconnect attempts and any strange popups
			self.has_error = true;
			self.ws.close();
		}
	};
};

DeFramed.prototype.announce = function(typ,txt,timeout,id){
	if(id === undefined) { id = typ; }
	var sel = `#df_ann_${id}`;

	var t = $(sel).attr("df_to")
	if (t) { clearTimeout(t); }

	$(sel).remove();
	if (txt === undefined || txt === null) { return; }

	var a = `
		<div id="df_ann_${id}" class="alert alert-dismissible alert-${typ}" role="alert">
			${txt}
		</div>
		`;
	$("#df_alerts").prepend(a);
	if (!(timeout < 0)) {
		$(sel).append(`
			<button type="button" class="close" data-dismiss="alert" aria-label="Close">
				<span aria-hidden="true">&times;</span>
			</button>
		`);
	}
	if(timeout > 0.1) {
		var fo = function() {
			// $(`#df_${typ}`).fadeOut(1000, function(e) { $(e).remove(); });
			$(sel).remove();
		};
		$(sel).attr("df_to", setTimeout(fo, timeout*1000));
	}
};

DeFramed.prototype.reconnect = function(){
	if (this.reconnect_timer) {
		clearTimeout(this.reconnect_timer);
		this.reconnect_timer = null;
	}
	this._setupWebsocket();
};

DeFramed.prototype._setupWebsocket = function(){
	var url = window.location.protocol.replace('http', 'ws') + '//' + window.location.host + '/ws';
	this.ws = new WebSocket(url);
	this.ws.binaryType = 'arraybuffer';
	this.has_error = false;
	var self = this;
	if (this.debug) console.log("WS START",url);

	this.ws.onclose = function(event){
		if (self.debug) console.log("WS CLOSE",event);
		if (self.has_error) { return; }
		self.announce("danger","Connection closed.<br /><a class=\"btn btn-outline-danger btn-sm\" href=\"#\" onclick=\"DF._setupWebsocket()\">Click here</a> to reconnect.");
	};

	this.ws.onerror = function (event) {
		if (self.debug) console.log("WS ERR",event);
		self.announce("danger","Connection error. Reconnecting soon.");
		if(self.backoff < 30000) { self.backoff = self.backoff * 1.5; }
		self.has_error = true;
		self.reconnect_timer = setTimeout(self._setupWebsocket, self.backoff);
	};

	this.ws.onmessage = function(event){
		var m = msgpack.decode(event.data);
		var action = m[0];
		m = m[1];
		if (self.debug) console.log("IN",action,m);
		var p = self["msg_"+action];
		if (p === undefined) {
			self.announce("warning",`Unknown message type '${action}'`);
		} else {
			try {
				p.call(self,m);
				if (self.backoff < 200) { self.backoff = self.backoff / 2; }
			} catch(e) {
				if (self.debug) console.log(e);
				self.announce("warning",`Message '${action}' caused error ${e}`)
			}
		}
	};

	this.ws.onopen = function (msg) {
		$("#df_spinner").show();
		self.announce("danger");
		self.send("first", {"uuid":self.uuid, "token":self.token, "version":window.deframed_version});
		self.announce("info",'Talking to the server. Stand by.');
	};
};

DeFramed.prototype.send = function(action,data) {
	if (this.debug) console.log("OUT",action,data);
	if(action == "reply") {
		if (this.debug) console.log("You can't reply here",data);
	} else {
		data = msgpack.encode([action,data]);
		if (this.ws) {
			this.ws.send(data);
		}
	}
};

DeFramed.prototype.msg_req = function(data) {
	var action=data[0];
	var n=data[1];
	data=data[2];
	try {
		data=this["req_"+action](data);
		if (this.debug) console.log("OUT","reply",n,data);
		this.ws.send(msgpack.encode(["reply",[n,data]]));
	} catch(e) {
		if (this.debug) console.log("OUT","reply",n,e,data);
		this.ws.send(msgpack.encode(["reply",[n,{"_error":e, "action":action, "n":n, "data":data}]]));
	}
};

DeFramed.prototype.msg_first = function(m) {
	this.version = m.version;
	this.uuid = m.uuid;
	sessionStorage.setItem('token', m.token);
	this.token = m.token;
	this.msg_busy(m.busy);
}

DeFramed.prototype.msg_reload = function(m) {
	location.reload(true);
}

DeFramed.prototype.msg_info = function(m) {
	this.announce(m.level, m.text, m.timeout);
	this.msg_busy(m.busy);
}

DeFramed.prototype.msg_fatal = function(m) {
	this.has_error = true;
	this.announce("danger",`${m}<br /><a class=\"btn btn-outline-danger btn-sm\" href=\"#\" onclick=\"DF.reconnect()\">Click here</a> to reconnect.`);
	this.msg_busy(m.busy);
}

DeFramed.prototype.msg_busy = function(m) {
	if(m === undefined) {}
	else if(m) { $("#df_spinner").show(); }
	else { $("#df_spinner").hide(); }
}

DeFramed.prototype.msg_modal = function(m) {
	var id = "#"+m[0];
	m = m[1];
	if(m === false) { $(id).modal('hide'); }
	else if(m === true) { $(id).modal('show'); }
	else { $(id).modal(m); }
}

DeFramed.prototype.msg_debug = function(m) {
	if(m === true) this.debug=true;
	else if(m === false) this.debug=false;
	else { console.log(m); }
	sessionStorage.setItem('debug', this.debug);
}

DeFramed.prototype.req_ping = function(m) {
	t = this.token;
	sessionStorage.setItem('token', m);
	this.token = m;
	return t;
}

DeFramed.prototype.msg_ping = function(m) {
	sessionStorage.setItem('token', m);
	this.token = m;
	this.send("pong",m);
}

DeFramed.prototype.msg_set = function(m) {
	var id = "#"+m[0]
	var pre = m[2]
	m = m[1]

	if (pre === true)
		$(id).prepend(m);
	else if (pre === false)
		$(id).append(m);
	else
		$(id).html(m);
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
	if(ele.onclick || !ele.id) { // already done
		return;
	}
	console.log('augmenting button: ', ele);
	var self = this;
	ele.onclick = function(){
		self.send("button",ele.id);
	}
};

DeFramed.prototype._augmentForm = function(ele){
	if(ele.onsubmit || !ele.id) { // already done
		return;
	}
	console.log('augmenting form: ', ele);
	var self = this;
	ele.onsubmit = function(){
		var res = {};
		for(var e of ele.elements) {
			if (e.name) {
				res[e.name] = e.value;
			}
		}
		self.send("form",[ele.id,res]);
		return false;
	}
};

DeFramed.prototype._elementActivated = function(action,ele){
	console.log('element activated:', ele);
	this.send(action, this._getActionURL(ele));
};

DeFramed.prototype.msg_remi_update = function(m) {
	var content = m[1];
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
	var elem = document.getElementById(m[0]);
	try {
		elem.insertAdjacentHTML('afterend',decodeURIComponent(m[1]));
		elem.parentElement.removeChild(elem);
	} catch(e) {
		/*Microsoft EDGE doesn't support insertAdjacentHTML for SVGElement*/
		var ns = document.createElementNS("http://www.w3.org/2000/svg",'tmp');
		ns.innerHTML = decodeURIComponent(m[1]);
		elem.parentElement.replaceChild(ns.firstChild, elem);
	}

	var elemToFocus = document.getElementById(focusedElement);
	if (elemToFocus != null) {
		elemToFocus.focus();
		try {
			elemToFocus = document.getElementById(focusedElement);
			if(caretStart>-1 && caretEnd>-1) elemToFocus.setSelectionRange(caretStart, caretEnd);
		} catch(e) {}
	}
}

DeFramed.prototype.req_eval = function(m) {
	return eval(m);
}

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
