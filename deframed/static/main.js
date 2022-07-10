// requires: msgpack https://unpkg.com/@msgpack/msgpack
//
'use strict';

var TextEnc = new TextEncoder();
var TextDec = new TextDecoder();

var ExtCodec = new MessagePack.ExtensionCodec();
ExtCodec.register({
	type: 4,
	encode: function(input, context) {
		if (input._deframed_var === undefined) {
			return null;
		}
		return TextEnc.encode(input._deframed_var);
	},
	decode: function(data, extType, context) {
		data = TextDec.decode(data);
		return context[data];
	},
});

var DeFramed = function(){
	self = this;
	this.has_error = false;
	this.token = sessionStorage.getItem('token');
	if (this.token === undefined || this.token == "undefined") this.token = null;
	this.version = null;
	this.backoff = 100;
	this.debug = sessionStorage.getItem('debug');
	this.reconnect_timer = null;
	this._setupListeners();
	this.vars = {};

	this.iframes = {};

	if (window.DF_parent_uuid) {
		this.parent = window.parent;
		window.addEventListener("message", this.receiveMessage, false);
	} else {
		this.parent = null;
		this._setupWebsocket();
	}

}

DeFramed.prototype.msg_encode = function(data) {
	return MessagePack.encode(data, { extensionCodec: ExtCodec, context: this.vars })
}

DeFramed.prototype.msg_decode = function(data) {
	return MessagePack.decode(data, { extensionCodec: ExtCodec, context: this.vars })
}

DeFramed.prototype.receiveMessage = function(event) {
	var m = event.data;
	if (m.dest == DF_uuid) { // from child
		var id = m.uuid;
		delete m.uuid;
		delete m.dest;
		this.sendCallbackParam(id,"from_iframe",m);
	} else if (this.parent) {
		this.parent.postMessage({"uuid":DF_uuid,
						         "dest":DF_parent_uuid, "id":id,
								 "fn":evt, "p":params
								}, "*");
	} else if (m.dest == DF_uuid && m.uuid == DF_parent_uuid) { // from parent
		this._dispatch(m.fn,m.p);
	}
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
		try {
			self.announce("danger","Connection error. Reconnecting soon.");
		} catch(e) {
			debugger;
		}
		if(self.backoff < 30000) { self.backoff = self.backoff * 1.5; }
		self.has_error = true;
		self.reconnect_timer = setTimeout(self._setupWebsocket, self.backoff);
	};

	this.ws.onmessage = function(event){
		var m = self.msg_decode(event.data);
		var action = m[0];
		m = m[1];
		self._dispatch(action,m);
	};
		

	this.ws.onopen = function (msg) {
		$("#df_spinner").show();
		self.announce("danger");
		self.send("setup", {"uuid":self.uuid, "token":self.token, "version":window.deframed_version});
		self.announce("info",'Talking to the server. Stand by.');
	};
};

DeFramed.prototype._dispatch = function(action,m) {
	if (this.debug) console.log("IN",action,m);
	var p = this["msg_"+action];
	if (p === undefined) {
		this.announce("warning",`Unknown message type '${action}'`);
	} else {
		try {
			p.call(this,m);
			if (this.backoff < 200) { this.backoff = this.backoff / 2; }
		} catch(e) {
			if (this.debug) console.log(e);
			this.announce("warning",`Message '${action}' caused error ${e}`)
		}
	}
};

DeFramed.prototype.send = function(action,data) {
	if (this.debug) console.log("OUT",action,data);
	if(action == "reply") {
		if (this.debug) console.log("You can't reply here",data);
	} else {
		data = this.msg_encode([action,data]);
		try {
			if (this.ws) {
				this.ws.send(data);
			}
		} catch(e) {
			console.log("Send failed",action,data);
		}
	}
};

DeFramed.prototype.msg_req = function(data) {
	var self = this;
	var action=data[0];
	var n=data[1];
	var store = data[3];
	data=data[2];

	var r_ok = function(data) {
		if (self.debug) console.log("OUT","reply",n,data);
		if (store !== undefined) {
			self.vars[store] = data;
			data = { "_deframed_var": store };
		}

		self.ws.send(self.msg_encode(["reply",[n,data]]));
	};
	var r_err = function(error) {
		if (self.debug) console.log("OUT","reply",n,error,data);
		self.ws.send(self.msg_encode(["reply",[n,{"_error":error+'', "action":action, "n":n, "data":data}]]));
	}
	try {
		data=this["req_"+action](data);
		if (data.then !== undefined) {
			data.then(r_ok).then(undefined, r_err);
			return;
		}
		r_ok(data);
	} catch(e) {
		r_err(e);
	}
};

DeFramed.prototype.msg_to_iframe = function(m) { // dest evt params
	var d = this.iframes[m[0]];
	d.contentWindow.postMessage({"uuid":DF_uuid, "dest":m[0],
							     "fn":m[1], "p":m[2]
							    }, "*");
};

DeFramed.prototype.msg_setup = function(m) {
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

DeFramed.prototype.msg_add_class = function(m) {
	var id = m.shift();
	var cl = document.getElementById(id).classList;
	for (var c in m)
		cl.add(c);
}

DeFramed.prototype.msg_remove_class = function(m) {
	var id = m.shift();
	var cl = document.getElementById(id).classList;
	for (var c in m)
		cl.remove(c);
}

DeFramed.prototype.msg_load_style = function(m) {
	var id = m.shift()
	m = m[0];
	if (!document.getElementById(id))
	{
		var head  = document.getElementsByTagName('head')[0];
		var link  = document.createElement('link');
		link.id   = id;
		link.rel  = 'stylesheet';
		link.type = 'text/css';
		link.href = m;
		link.media = 'all';
		head.appendChild(link);
	}
}

DeFramed.prototype.msg_set_attr = function(m) {
	var e = document.getElementById(m[0]);
	m = m[1];
	Object.keys(m).forEach(k => {
		e.setAttribute(k,m[k]);
	}
	);
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

DeFramed.prototype.req_token = function(m) {
	t = this.token;
	sessionStorage.setItem('token', m);
	this.token = m;
	return t;
}

DeFramed.prototype.req_elem_info = function(m) {
	var e = document.getElementById(m);
	if (e === null)
		return null;
	return { 'height':e.scrollHeight
			, 'width':e.scrollWidth
			, 'view':e.getBoundingClientRect().toJSON()
			};
}

DeFramed.prototype.msg_ping = function(m) {
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

DeFramed.prototype.req_get_attr = function(m) {
	res = []

	Object.keys(m).forEach(k => {
		var v = m[k];
		var e = document.getElementById(k);
		if (e === undefined)
			res.push(null);
		else if(!e.hasAttributes)
			res.push({});
		else {
			var r = {};
			var attrs = e.attributes;
			for(var i = attrs.length - 1; i >= 0; i--) 
				r[attrs[i].name] = attrs[i].value;
			res[k] = r;
		}
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

DeFramed.prototype.msg_elem = function(m) {
	var elem = document.getElementById(m[0]);
	m = m[1];
	var focusedElement=null;
	var caretStart=-1;
	var caretEnd=-1;
	if (document.activeElement) {
		focusedElement = document.activeElement.id;
		try {
			caretStart = document.activeElement.selectionStart;
			caretEnd = document.activeElement.selectionEnd;
		} catch(e) {}
	}
	//try {
		elem.insertAdjacentHTML('afterend',m);
		elem.parentElement.removeChild(elem);
	//} catch(e) {
		///*Microsoft EDGE doesn't support insertAdjacentHTML for SVGElement*/
		//var ns = document.createElementNS("http://www.w3.org/2000/svg",'tmp');
		//ns.innerHTML = m;
		//elem.parentElement.replaceChild(ns.firstChild, elem);
	//}

	if (focusedElement) {
		var elemToFocus = document.getElementById(focusedElement);
		if (elemToFocus != null) {
			elemToFocus.focus();
			try {
				elemToFocus = document.getElementById(focusedElement);
				if(caretStart>-1 && caretEnd>-1) elemToFocus.setSelectionRange(caretStart, caretEnd);
			} catch(e) {}
		}
	}
}

DeFramed.prototype.req_eval = function(m) {
	var res;
	if (typeof m === 'string') {
		res = eval(m);
	} else {
		res = eval(m.str);
		if (m.args !== undefined) {
			var args = [];
			for (var c of m.args) {
				if (c._deframed_var !== undefined) {
					c = this.vars[c._deframed_var];
				}
				args.push(c);
			}
			res = res(... args);
		}
	}
	return res;
}

// remi support
DeFramed.prototype.sendCallback = function(id,evt) {
	this.sendCallbackParam(id,evt,null);
}

DeFramed.prototype.sendCallbackParam = function(id,evt,params) {
	if (this.parent)
		this.parent.postMessage({"a":"call", "uuid":DF_uuid,
						         "dest":DF_parent_uuid, "id":id,
								 "fn":evt, "p":params
								}, "*");
	else
		this.send("remi_event",[id,evt,params]);
}

$(function() {
	window.DF = new DeFramed();
	window.remi = window.DF; // remi support
	$("#init_alert").remove();

	$("a").attr("draggable",false);

	// This is a simple handler to scale the main area so that header
	// and footer don't obscure the main area.
	// TODO: use a ResizeObserver to handle changes to header and footer height.
	$(window).on('resize',function(evt) {
		var hh = $('header').height();
		var hb = $('body').height();
		var hf = $('footer').height();
		var wb = $('body').width();
		if (!(hh >= 0)) hh = 0;
		if (!(hf >= 0)) hf = 0;
		$('main').offset({top:hh, left:0});
		var hm = hb-hh-hf; // height for main area
		$('main').height(hm);
		DF.send('size',{'height':hb,'width':wb,'header':hh,'footer':hf})
	});
	$(window).trigger('resize');
})
