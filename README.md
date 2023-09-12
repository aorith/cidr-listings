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

Safelists exist exclusively to filter the denylists, when you add an address to an **enabled** safelist, that address is removed from all the existing denylists and when you enable a disabled safelist all the denylists are filtered with the addresses of that safelist.  

For example, if you have the following networks/addresses in a denylist (or spread in many denylist it doesn't matter):

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

The denylists will be filtered and finally they will have the following:

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

This also works if you try to add the original addresses to the denylist when a safelists is present, basically safelists act as a filter for denylists.  

#### About address exclusion

Excluding a network from another is easy with the `ipaddress` python library:

```python
import ipaddress

a = ipaddress.ip_network("1.1.0.0/16")
b = ipaddress.ip_network("1.1.1.0/24")

for i in a.address_exclude(b):
    print(i)
```

```
# Output:
1.1.128.0/17
1.1.64.0/18
1.1.32.0/19
1.1.16.0/20
1.1.8.0/21
1.1.4.0/22
1.1.2.0/23
1.1.0.0/24
```

That is when you have to exclude one-from-one but when you have thousands of addresses (safe addresses) that should exclude recursively another set of thousands of addresses (deny addresses) things start to complicate.  
After you exclude address `a` with address `b` (checking if `b` is contained in `a` of course) you might end up with:

- Nothing, if `b` is a supernet of `a` (you cannot use `address_exclude` directly here and must check explicitly if `b` is a supernet of `a`)
- Nothing if `b` is equal to `a`
- One or many subnets if `b` is a subnet of `a`)
- The original address `a` if `b` just doesn't exclude anything from `a`

When you end up with one or multiple extra subnets after an exclusion, you need to iterate over them again to ensure that they are fully excluded with your "safe addresses". That can become very slow since you cannot be sure on how many times you need to iterate until everything is excluded correctly.  

### Installation & development

The scripts [run-postgres-prod.sh](run-postgres-prod.sh) and [run-app-prod.sh](run-app-prod.sh) provide an example on how to run the app, the database must be up and running before starting the app.  

To develop locally, run `make install` to create a *venv* with all the dependencies, `make test` always starts an empty database and runs all the tests.  
The app can be started by running the `litestar` cli tool: `cd src; litestar run --reload`.  
That's what I solved for my usecase with the following functions:

- This is were the background job that filters addresses starts - [filter_safe_cidrs](https://github.com/aorith/cidr-listings/blob/e2b89e98784ce80c4ca32c7a88724ace667db5c0/src/app/lib/worker.py#L130-L136)
- This takes an address and filters it using many addresses - [address_exclude_many](https://github.com/aorith/cidr-listings/blob/e2b89e98784ce80c4ca32c7a88724ace667db5c0/src/app/lib/iputils.py#L86)
- This is a faster implementation of python's `ipaddress/address_exclude` and is called by `address_exclude_many` - [exclude_address_raw](https://github.com/aorith/cidr-listings/blob/e2b89e98784ce80c4ca32c7a88724ace667db5c0/src/app/lib/iputils.py#L12)

### Usage

1. Create as many denylists as you need, either by using the web interface or with the API, tag them according to your needs.  
2. Create one or many **enabled** safelists, and add all the addresses that should never be present in a denylist. If you add more in the future, denylists will be filtered automatically.
3. Consume the denylists by *tags* using the endpoints `/v1/cidr/.*`, for example `/v1/cidr/collapsed` returns all the matched addresses collapsed into networks.

### License

[LICENSE](LICENSE) ([MIT](https://spdx.org/licenses/MIT.html))
