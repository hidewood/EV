# Cloudflare Tunnel 本地项目公网部署手册

本文档用于说明如何使用 Cloudflare Tunnel 将本地运行的 Web 项目发布到公网域名。文档目标是：以后换域名、换项目、换端口，或者把另一个项目部署到同一个域名时，可以直接把本文档交给另一个 AI 或开发者照着操作。

## 1. 方法原理

Cloudflare Tunnel 的部署方式不是把代码上传到 Cloudflare，而是：

```text
用户浏览器
  -> https://你的域名
  -> Cloudflare 边缘网络
  -> cloudflared tunnel
  -> 你的本机服务，例如 http://127.0.0.1:8080
```

也就是说：

- 项目仍然运行在本机。
- 公网流量通过 Cloudflare 转发到本机。
- 只要本机项目或 `cloudflared` 停止运行，公网域名就无法访问。
- Named Tunnel 可以使用固定域名，比 `trycloudflare.com` 的临时 quick tunnel 稳定。

## 2. 当前项目部署现状

当前域名：

```text
https://comgender-blog.top
```

当前 tunnel：

```text
NAME: dbdesign
ID: 465534cd-8e31-40dd-9538-c9b30c9bc685
```

当前 Cloudflare Tunnel 配置文件：

```text
C:\Users\HIDE\.cloudflared\config.yml
```

当前配置内容：

```yaml
tunnel: 465534cd-8e31-40dd-9538-c9b30c9bc685
credentials-file: C:\Users\HIDE\.cloudflared\465534cd-8e31-40dd-9538-c9b30c9bc685.json

ingress:
  - hostname: comgender-blog.top
    service: http://127.0.0.1:8080
  - service: http_status:404
```

含义：

```text
comgender-blog.top -> 本机 127.0.0.1:8080
```

## 3. 前置条件

### 3.1 域名已接入 Cloudflare

域名必须已经添加到 Cloudflare，并且域名的 NS 服务器已经改成 Cloudflare 提供的 NS。

检查方法：

```powershell
Resolve-DnsName comgender-blog.top
```

如果能解析出 Cloudflare 的 IP，说明 DNS 基本正常。

### 3.2 已安装 cloudflared

当前机器安装路径：

```text
C:\Program Files (x86)\cloudflared\cloudflared.exe
```

检查版本：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" --version
```

### 3.3 已登录 Cloudflare

登录命令：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel login
```

如果出现：

```text
You have an existing certificate at C:\Users\HIDE\.cloudflared\cert.pem
```

说明已经登录过，不需要重复登录，也不要随便删除 `cert.pem`。

## 4. 标准部署流程

### 4.1 启动本地项目

先确认项目在本机可以打开。例如当前项目运行在 `8080`：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/ -TimeoutSec 5
```

如果返回 `200 OK`，说明本地服务正常。

### 4.2 创建 named tunnel

如果已经有可复用 tunnel，可以跳过本步骤。

创建新 tunnel：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel create charging-system
```

查看 tunnel 列表：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel list
```

输出中会看到：

```text
ID                                   NAME
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx charging-system
```

记下 `ID` 和 `NAME`。

### 4.3 绑定域名到 tunnel

如果要把根域名绑定到 tunnel：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel route dns charging-system example.com
```

如果要绑定子域名：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel route dns charging-system app.example.com
```

当前项目曾执行过类似命令：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel route dns dbdesign comgender-blog.top
```

### 4.4 编写 config.yml

配置文件路径：

```text
C:\Users\HIDE\.cloudflared\config.yml
```

标准模板：

```yaml
tunnel: <tunnel-id>
credentials-file: C:\Users\HIDE\.cloudflared\<tunnel-id>.json

ingress:
  - hostname: <your-domain>
    service: http://127.0.0.1:<local-port>
  - service: http_status:404
```

示例：

```yaml
tunnel: 465534cd-8e31-40dd-9538-c9b30c9bc685
credentials-file: C:\Users\HIDE\.cloudflared\465534cd-8e31-40dd-9538-c9b30c9bc685.json

ingress:
  - hostname: comgender-blog.top
    service: http://127.0.0.1:8080
  - service: http_status:404
```

注意：

- 最后一条 `- service: http_status:404` 必须保留。
- `hostname` 必须和实际访问域名一致。
- `service` 必须指向本机真实可访问的端口。

### 4.5 校验配置

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel ingress validate
```

看到：

```text
OK
```

说明配置文件格式正确。

### 4.6 启动 tunnel

前台启动：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run charging-system
```

如果使用当前已有 tunnel：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run dbdesign
```

启动成功后会看到类似：

```text
Registered tunnel connection
```

此时即可访问：

```text
https://你的域名
```

## 5. 部署另一个项目到同一个根域名

假设新项目本地运行在：

```text
http://127.0.0.1:3000
```

如果要让：

```text
https://comgender-blog.top
```

指向新项目，只需要修改 `config.yml`：

```yaml
tunnel: 465534cd-8e31-40dd-9538-c9b30c9bc685
credentials-file: C:\Users\HIDE\.cloudflared\465534cd-8e31-40dd-9538-c9b30c9bc685.json

ingress:
  - hostname: comgender-blog.top
    service: http://127.0.0.1:3000
  - service: http_status:404
```

然后重启 tunnel：

```powershell
Stop-Process -Name cloudflared -ErrorAction SilentlyContinue
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run dbdesign
```

注意：这会让原来的项目不再占用 `comgender-blog.top`。

## 6. 部署多个项目到不同子域名

推荐方式是给每个项目分配不同子域名。

示例：

```text
https://app.comgender-blog.top  -> 本机 127.0.0.1:3000
https://api.comgender-blog.top  -> 本机 127.0.0.1:5000
https://charge.comgender-blog.top -> 本机 127.0.0.1:8080
```

先分别绑定 DNS：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel route dns dbdesign app.comgender-blog.top
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel route dns dbdesign api.comgender-blog.top
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel route dns dbdesign charge.comgender-blog.top
```

然后配置：

```yaml
tunnel: 465534cd-8e31-40dd-9538-c9b30c9bc685
credentials-file: C:\Users\HIDE\.cloudflared\465534cd-8e31-40dd-9538-c9b30c9bc685.json

ingress:
  - hostname: app.comgender-blog.top
    service: http://127.0.0.1:3000
  - hostname: api.comgender-blog.top
    service: http://127.0.0.1:5000
  - hostname: charge.comgender-blog.top
    service: http://127.0.0.1:8080
  - service: http_status:404
```

## 7. 同一个域名按路径转发到不同项目

如果必须用同一个域名，也可以按路径转发。

示例：

```text
https://comgender-blog.top/api/* -> 本机 127.0.0.1:5000
https://comgender-blog.top/*     -> 本机 127.0.0.1:3000
```

配置：

```yaml
tunnel: 465534cd-8e31-40dd-9538-c9b30c9bc685
credentials-file: C:\Users\HIDE\.cloudflared\465534cd-8e31-40dd-9538-c9b30c9bc685.json

ingress:
  - hostname: comgender-blog.top
    path: ^/api/.*
    service: http://127.0.0.1:5000
  - hostname: comgender-blog.top
    service: http://127.0.0.1:3000
  - service: http_status:404
```

注意：

- 更具体的规则必须写在前面。
- 兜底规则写在后面。
- 最后一条 `http_status:404` 必须保留。

## 8. 换成另一个域名部署

假设新域名是：

```text
example.com
```

步骤：

1. 把 `example.com` 添加到 Cloudflare。
2. 修改域名 NS 到 Cloudflare。
3. 确认 cloudflared 已登录。
4. 绑定 DNS：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel route dns dbdesign example.com
```

5. 修改 `config.yml`：

```yaml
tunnel: 465534cd-8e31-40dd-9538-c9b30c9bc685
credentials-file: C:\Users\HIDE\.cloudflared\465534cd-8e31-40dd-9538-c9b30c9bc685.json

ingress:
  - hostname: example.com
    service: http://127.0.0.1:8080
  - service: http_status:404
```

6. 重启 tunnel：

```powershell
Stop-Process -Name cloudflared -ErrorAction SilentlyContinue
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run dbdesign
```

## 9. 常用检查命令

### 9.1 检查本地项目是否正常

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/ -TimeoutSec 5
```

### 9.2 检查 tunnel 列表

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel list
```

### 9.3 查看 tunnel 详情

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel info dbdesign
```

### 9.4 校验 ingress 配置

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel ingress validate
```

### 9.5 检查 cloudflared 进程

```powershell
Get-Process cloudflared -ErrorAction SilentlyContinue
```

### 9.6 停止所有 cloudflared 进程

```powershell
Stop-Process -Name cloudflared -ErrorAction SilentlyContinue
```

### 9.7 检查域名 DNS

```powershell
Resolve-DnsName comgender-blog.top
```

### 9.8 查看 metrics

cloudflared 通常会暴露本地 metrics：

```text
http://127.0.0.1:20241/metrics
```

访问：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:20241/metrics -TimeoutSec 5
```

可关注：

```text
cloudflared_tunnel_total_requests
cloudflared_tunnel_response_by_code
cloudflared_tunnel_request_errors
cloudflared_tunnel_ha_connections
```

## 10. 常见问题

### 10.1 访问域名返回 404

可能原因：

- `config.yml` 的 `hostname` 和访问域名不一致。
- 访问的是旧的 quick tunnel 地址。
- tunnel 没有重启，仍在使用旧配置。
- 最后一条 `http_status:404` 被命中，说明没有匹配到前面的 ingress 规则。

处理：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel ingress validate
Stop-Process -Name cloudflared -ErrorAction SilentlyContinue
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run dbdesign
```

### 10.2 访问域名连接失败

可能原因：

- 本地项目没有启动。
- 本地端口写错。
- cloudflared 没有运行。
- 域名还没有正确接入 Cloudflare。

处理：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:<local-port>/ -TimeoutSec 5
Get-Process cloudflared -ErrorAction SilentlyContinue
Resolve-DnsName <your-domain>
```

### 10.3 多个 cloudflared 同时运行

多个进程可能导致你不知道当前哪个 tunnel 在生效。

建议先全部停止，再只启动一个：

```powershell
Stop-Process -Name cloudflared -ErrorAction SilentlyContinue
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run dbdesign
```

### 10.4 代理导致浏览器打不开

如果系统代理指向不可用端口，浏览器可能无法访问 Cloudflare 域名。

检查代理：

```powershell
Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' | Select-Object ProxyEnable,ProxyServer,AutoConfigURL
```

如果代理开启但代理软件没有运行，需要关闭系统代理或启动代理软件。

### 10.5 修改 config.yml 后没有生效

修改配置后必须重启 cloudflared：

```powershell
Stop-Process -Name cloudflared -ErrorAction SilentlyContinue
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run dbdesign
```

## 11. 交给另一个 AI 的部署提示词

可以把下面这段直接发给另一个 AI：

```text
请根据本机 Cloudflare Tunnel 配置部署项目。

系统是 Windows PowerShell。
cloudflared 路径：
C:\Program Files (x86)\cloudflared\cloudflared.exe

Cloudflare 配置目录：
C:\Users\HIDE\.cloudflared

当前已有 named tunnel：
NAME: dbdesign
ID: 465534cd-8e31-40dd-9538-c9b30c9bc685

当前 credentials 文件：
C:\Users\HIDE\.cloudflared\465534cd-8e31-40dd-9538-c9b30c9bc685.json

请完成以下任务：
1. 确认本地项目已经在指定端口运行。
2. 如果要使用 comgender-blog.top，则修改 C:\Users\HIDE\.cloudflared\config.yml，把 hostname 设置为 comgender-blog.top，把 service 设置为本地项目地址，例如 http://127.0.0.1:8080。
3. 如果要使用新域名或子域名，先执行 cloudflared tunnel route dns dbdesign <hostname>。
4. 执行 cloudflared tunnel ingress validate 校验配置。
5. 停止已有 cloudflared 进程。
6. 执行 cloudflared tunnel run dbdesign 启动 tunnel。
7. 用浏览器访问 https://<hostname> 验证。

注意：
- config.yml 最后一条必须是 - service: http_status:404。
- hostname 必须和浏览器访问的域名一致。
- service 必须是本机真实可访问的地址。
- 修改 config.yml 后必须重启 cloudflared。
- 不要使用 trycloudflare.com 临时地址做正式验收。
```

## 12. 当前项目快速启动参考

当前智能充电桩项目本地启动：

```powershell
venv\Scripts\Activate.ps1
python run.py
```

确认本机服务：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/ -TimeoutSec 5
```

启动 Cloudflare Tunnel：

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run dbdesign
```

访问：

```text
https://comgender-blog.top
```
