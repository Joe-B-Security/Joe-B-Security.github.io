---
title: "Finding Unblocked Vectors for XSS"
date: 2022-07-28
description: "A technique for discovering which XSS tags and attributes bypass security filters using Burp Suite"
tags: ["XSS", "Bug Bounty", "Burp Suite"]
---

When you have that feeling an input is vulnerable to XSS but something is blocking or removing the payload, you can use this relatively simple trick using Burp Suite's Intruder to discover which XSS tags and attributes are able to bypass the block.

It should be somewhat obvious when you input a value containing a common XSS payload that the request is being blocked or stripped, it could be by a piece of custom code or a WAF.

The request:

> `GET /?search=test HTTP/1.1`

is returning:

> `HTTP/1.1 200 OK`

However:

> `GET /?search=<svg/onload=prompt()>`

is returning:

> `HTTP/1.1 400 Bad Request`

or perhaps:

> `GET /?search=<script>test</script> HTTP/1.1`

has its tags stripped and searching for:

> `0 search results for 'test'`

Thanks to the great work done by [Port Swigger research](https://twitter.com/PortSwiggerRes), we have a comprehensive and regularly updated [cheat sheet](https://portswigger.net/web-security/cross-site-scripting/cheat-sheet) for XSS events and tags.

Let's go ahead and send the request to Intruder and highlight the input between the tags `< >`

![img](https://i.imgur.com/7iyQD4Y.png)

Next, visit the cheat sheet and scroll down to *Event handlers* and click *Copy tags to clipboard*

![img](https://i.imgur.com/h7ZSW1X.png)

Go back to intruder and in the *Payloads* tab, have *Payload type* as *Simple list* and click *Paste* for *Payload Options* and start the attack

![img](https://i.imgur.com/YA54WBp.png)

View the results and if you're lucky, you might get a few different responses for certain tags:

![img](https://i.imgur.com/l5B9p8y.png)

Now we know the `<body>` tag is not being blocked or stripped, let's move onto building the rest of our XSS payload and add an event. Go back to intruder, add `<body` to the value, include a `%20` to include a URL friendly space, and highlight where we will add the event and finally add a `=` which will be in our final XSS payload:

![img](https://i.imgur.com/0zLRZ5x.png)

This time go back to the cheat sheet and click *Copy events to clipboard*, go back to the *Payloads* tab, clear the previous *Payload Options* and *Paste* in the events and start the attack.

View the results and if you're lucky again you will get some different responses for certain events:

![img](https://i.imgur.com/RMnmdno.png)

Now we have successfully got a tag and event bypassed, and an XSS fired off!

![img](https://i.imgur.com/mgF8oDu.png)

![img](https://i.imgur.com/QxNkggO.png)