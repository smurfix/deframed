========
DeFramed
========

What the …
++++++++++

Deframed is a non-framework for web programming. In fact it is the very
antithesis of a web framework.

Huh?
----

The basic idea of building web pages, these days, is to delegate as much as
possible to the client. The problem is that if you don't want to do that,
but still like to offer a single-page site to your user, you're on your
own.

Why?
----

Well, maybe Javascript is a truly annoying language. To you, anyway. Maybe
your site logic is Secret Sauce and shouldn't end up in the browser. Maybe
your API shouldn't be exposed to the outside world. Maybe you want to tell
the browser what to display. Maybe you just want to build a Web UI that
behaves like any other UI, i.e. read events from the user and tell the
screen what to display, period end of story.

Whatever your reason, DeFramed's purpose is to make sure that you won't
have to deal with programming on the browser side. No more than absolutely
necessary, anyway.

Principle of operation
++++++++++++++++++++++

Client
------

DeFramed displays a generic initial page and starts a small Javascript
handler that connects to a web socket on your server. It then proxies a
handful of DOM manipulation functions and exports a few calls which your
user-facing interface elements can use to send events or data to the
server.

There's also basic support for a client-side spinner, a simple way to show
alerts if/when the connection breaks, templating (with Mustache) so you
don't need to send redundant data, and rudimentary access to local data to
store the equivalent of a cookie and to stash templates on the client. Oh
yes, and some rudimentary DOM manipulation, like adding a class to some
element.

DeFramed also auto-adds "onclick" handlers to each button and "onsubmit"s
to each form (assuming they have an ID and no existing handler), so you
don't have to.

Note the absence of anything that could be interpreted as client-side
logic, which is why DeFramed is a non-framework.

Server
------

If there is zero client-side logic, the server needs to handle everything.
(Which it has to do anyway.) Thus, DeFramed includes classes to support all
of this.

The DeFramed server is based on Quart-Trio, thus it natively supports async
operations. It uses Trio instead of asyncio: cleanly shutting down a
complex asyncio application is a debugging exercise nobody should undergo.
You can ignore the async stuff, but as soon as you call out to a database
you probably don't want to.

Each client's events are processed sequentially, though it's easy to run a
background task – which is guaranteed to get terminated when the client
disconnects or times out.

