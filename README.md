![](src/app/domain/web/statics/static/img/logo.png)

### Description

I created this app because I wanted to learn and experiment with:

- [Litestar](https://litestar.dev/)
- [Postgres](https://www.postgresql.org/) without ORM
- Postgres [as a job queue](https://github.com/aorith/cidr-listings/blob/2776c832005e0fb128f543393926aec9201d16d5/src/app/lib/worker.py#L22-L28)
- Simple and custom [DB migrations script](https://github.com/aorith/cidr-listings/blob/2776c832005e0fb128f543393926aec9201d16d5/src/app/lib/db/migrations.py)
- [Asyncpg](https://github.com/MagicStack/asyncpg)
- [Msgspec](https://github.com/jcrist/msgspec) instead of [pydantic](https://github.com/pydantic/pydantic)
- [JWT](https://github.com/aorith/cidr-listings/blob/2776c832005e0fb128f543393926aec9201d16d5/src/app/domain/auth/jwt.py) [(Json Web Token)](.org/wiki/JSON_Web_Token)
- [HTMX](https://htmx.org/)
- Some magic to [exclude a network from another](https://github.com/aorith/cidr-listings/blob/2776c832005e0fb128f543393926aec9201d16d5/src/app/lib/iputils.py#L12) faster than the builtin python `address_exclude`.

This app allows you to create lists of IP addresses in their [CIDR notation](https://en.wikipedia.org/wiki/Classless_Inter-Domain_Routing#CIDR_notation).  
Lists have two types:  

- denylist
- safelist

Safelists exist exclusively to filter the denylists, when you add a network to an **enabled** safelist, that network is removed from all the existing denylists and when you enable a disabled safelist all the denylists are filtered with the networks of that safelist.  

For example, if you have the following networks in a denylist (or spread in many denylist it doesn't matter):

```
66.66.1.0/24
12.12.1.0/24
```

And you create a safelist with the following networks:

```
66.66.1.0/26
12.12.1.10/32
12.12.1.12/32
```

The denylists will be filtered and finally they will have the following networks:

```
12.12.1.0/29
12.12.1.11/32
12.12.1.128/25
12.12.1.13/32
12.12.1.14/31
12.12.1.16/28
12.12.1.32/27
12.12.1.64/26
12.12.1.8/31
66.66.1.128/25
66.66.1.64/26
```

### Installation

### Usage

### License

[LICENSE](LICENSE) ([MIT](https://spdx.org/licenses/MIT.html))
