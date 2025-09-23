---
title: "Bypassing Samesite Cookie Restrictions with Method Override"
date: 2023-07-30
description: "A technique for bypassing SameSite cookie restrictions using HTTP method override features in web frameworks"
tags: ["Bug Bounty", "CSRF"]
---

Browsers, in an attempt to mitigate CSRF (Cross-Site Request Forgery) attacks, have introduced the [SameSite cookie attribute](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#samesite-cookie-attribute).

By default, cookies are set to `SameSite=Lax`, which stops the cookie from being sent during cross-site requests, unless they are initiated by top-level navigations via `GET` requests. This effectively protects against CSRF attacks launched through `POST` requests.

However, a loophole exists. A number of web development frameworks support the override of HTTP methods at the server-side. An attacker can exploit this by altering a POST request to a `GET`, thereby bypassing the SameSite cookie restrictions and successfully performing CSRF attacks.

## How Method Override Works

Method Override is a functionality that allows the HTTP method processed by the server to be different from the one specified in the initial request. Here are some typical ways to override methods:

- Hidden form fields, such as `_method=PUT`
- Custom HTTP headers, for instance `X-HTTP-Method-Override: DELETE`
- Server-side middleware capable of parsing these overrides

These techniques are frequently used to emulate `PUT`, `PATCH`, and `DELETE` requests in web forms, which by design, only support `GET` and `POST` natively.

## Bypassing Lax Restrictions with GET Requests

In real-world scenarios, servers aren't always strict about the HTTP method they receive for a given endpoint. This is often the case even for endpoints that traditionally expect a form submission via a `POST` request. If such servers also employ Lax restrictions for their session cookies - either explicitly or due to the default settings of the browser - it opens up a potential avenue for CSRF attacks by triggering a `GET` request from the victim's browser.

As long as the `GET` request initiates a top-level navigation, the browser will still append the victim's session cookie. This creates a viable path for launching a CSRF attack. Let's take a look at one of the simplest methods to execute such an attack:


```javascript
<script>
  document.location = 'https://example.com/transfer?recipient=attacker&amount=1000';
</script>
```

Even when ordinary GET requests are disallowed, several frameworks provide mechanisms to override the HTTP method stated in the request line. For example, the Symfony framework supports the _method parameter within forms. This parameter takes precedence over the usual method for routing decisions:

## Leveraging Method Override Example

Frameworks like Symfony allow the method to be overridden using `_method` parameters:

```html
<form action="https://example.com/transfer" method="POST">
  <input type="hidden" name="_method" value="GET">
  <input type="hidden" name="recipient" value="attacker">
  <input type="hidden" name="amount" value="1000">
</form>
```

The server is deceived into treating the `POST` request as a `GET` request demonstrating the principle of method override, and how it can be used to manipulate the server-side routing logic. A variety of similar parameters are supported by other frameworks, further extending the potential for such exploits:


## Frameworks With Built-In Support

Here is a summary of some popular web frameworks and how they allow method override:

| Framework | Parameter | Method Override Header | Notes |
|:------|:------|:------|:------|
| Symfony | `_method` | `X-HTTP-Method-Override` | |
| Rails | `_method` | `X-HTTP-Method-Override` | |
| Laravel | `_method` | `X-HTTP-Method-Override` | |
| CodeIgniter | `_method` | `X-HTTP-Method-Override` | |
| CakePHP | `_method` | `X-HTTP-Method-Override` | |
| Yii | `_method` | `X-HTTP-Method-Override` | |
| Flask | - | `X-HTTP-Method-Override` | |
| Django | - | `X-HTTP-Method-Override` | |
| Angular | - | - | Depends on the HTTP library used |
| React | - | - | Depends on the HTTP library used |
| Vue.js | - | - | Depends on the HTTP library used |
| Ember.js | `_method` | `X-HTTP-Method-Override` | |
| Meteor | `_method` | - | |
| Express.js | `_method` | `X-HTTP-Method-Override` | Via middleware |
| Koa.js | `_method` | `X-HTTP-Method-Override` | Via middleware |
| Next.js | - | - | Depends on the HTTP library used |
| Spring MVC | - | `X-HTTP-Method-Override` | |
| ASP.NET Core | - | `X-HTTP-Method-Override` | With middleware support |
| Phoenix | `_method` | `X-HTTP-Method-Override` | |
| Bottle | `_method` | `X-HTTP-Method-Override` | |

## Crafting the Exploit

After identifying a potential request on an identified framework, as an attacker it's trivial to craft this exploit to trigger the malicious `GET` request e.g.

```html
<script>
  document.location = "https://hazanasec.github.io/send?amount=1000&_method=POST";
</script>
```

When loaded by the unsuspecting victim, this script bypasses the Lax restrictions and performs the intended action on behalf of the victim.

In conclusion, while the SameSite cookie attribute has added a layer of defense against CSRF attacks, it's essential to be aware of its limitations and potential workarounds. Method override, in certain circumstances, could be exploited by attackers to bypass these protections, happy hacking!