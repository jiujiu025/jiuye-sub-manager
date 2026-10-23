<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">资源池</h2>
        <p class="page-subtitle">统一查看、筛选、编辑与导出当前节点池。</p>
      </div>
      <div class="page-header-mark"><el-icon><Grid /></el-icon><span>NODE POOL</span></div>
    </div>
    <div class="filter-bar">
      <div class="spacer" />
      <el-button :disabled="!selected.length" @click="batchAction('enable')">批量启用</el-button>
      <el-button :disabled="!selected.length" @click="batchAction('disable')">批量禁用</el-button>
      <el-button type="warning" plain :disabled="!selected.length" @click="openBatchForward">批量转发</el-button>
      <el-button type="danger" plain :disabled="!selected.length" @click="batchAction('delete')">批量删除</el-button>
      <el-button :loading="countryResolving" @click="resolveCountries">识别空白地区</el-button>
      <el-button type="success" plain :loading="healthCheckingAll" @click="checkAllHealth">全部检测</el-button>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>
        导入外部节点
      </el-button>
    </div>

    <div class="node-scope-tabs">
      <el-tabs v-model="nodeScope" @tab-change="changeNodeScope">
        <el-tab-pane label="全部节点" name="all" />
        <el-tab-pane label="上游订阅节点" name="subscription" />
        <el-tab-pane label="导入外部节点" name="custom" />
        <el-tab-pane label="已转发节点" name="forwarded" />
      </el-tabs>
      <span class="scope-hint">上游订阅节点按来源区分；导入外部节点包含链接导入和手动录入</span>
    </div>

    <div class="surface-card node-filters-card">
    <el-form inline class="filters">
      <el-form-item label="关键词">
        <el-input v-model="filters.keyword" clearable placeholder="名称/服务器" @keyup.enter="load" />
      </el-form-item>
      <el-form-item label="上游来源">
        <el-select v-model="filters.source_name" clearable filterable placeholder="全部来源" @change="load">
          <el-option v-for="source in sourceFilterOptions" :key="source" :label="source" :value="source" />
        </el-select>
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="filters.node_type" clearable placeholder="全部" @change="load">
          <el-option v-for="option in protocolOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="地区">
        <el-select v-model="filters.country" clearable placeholder="全部" @change="load">
          <el-option v-for="country in countryOptions" :key="country" :label="country" :value="country" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="load">查询</el-button>
      </el-form-item>
    </el-form>
    </div>

    <div class="surface-card node-table-card">
      <el-table
        :data="rows"
        :row-class-name="tableRowClassName"
        v-loading="loading"
        @selection-change="(items) => (selected = items.map((item) => item.id))"
      >
      <el-table-column type="selection" width="45" />
      <el-table-column prop="node_code" label="编号" width="105" />
      <el-table-column prop="name" label="名称" min-width="150" />
      <el-table-column prop="type" label="类型" width="110" />
      <el-table-column label="地区" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.country" type="success" effect="plain">{{ row.country }}</el-tag>
          <el-tag v-else type="info" effect="plain">待识别</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="server" label="服务器" min-width="150" show-overflow-tooltip />
      <el-table-column prop="port" label="端口" width="80" />
      <el-table-column label="来源" width="110">
        <template #default="{ row }">{{ sourceLabel(row) }}</template>
      </el-table-column>
      <el-table-column label="转发服务器" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="row.node_category === 'forwarded'">
            <strong>{{ row.forward_target_server_name || '-' }}</strong>
            <small class="forward-endpoint">{{ row.forward_target_server_address || '未配置地址' }}</small>
          </template>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="入站信息" min-width="190" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="row.node_category === 'forwarded'">
            <strong>{{ row.forward_inbound_remark || '未命名入站' }}</strong>
            <small class="forward-endpoint">{{ row.forward_inbound_endpoint || '-' }} · ID {{ row.forward_inbound_id || '-' }}</small>
          </template>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">{{ row.note || '-' }}</template>
      </el-table-column>
      <el-table-column label="资源到期" width="170">
        <template #default="{ row }">{{ row.expires_at ? formatTime(row.expires_at) : '长期有效' }}</template>
      </el-table-column>
      <el-table-column label="最近发现" width="155">
        <template #default="{ row }">{{ formatTime(row.last_seen_at) }}</template>
      </el-table-column>
      <el-table-column label="健康状态" width="125">
        <template #default="{ row }">
          <el-tooltip v-if="row.health_detail" :content="row.health_detail" placement="top">
            <el-tag :type="healthTagType(row.health_status)">{{ healthLabel(row.health_status) }}</el-tag>
          </el-tooltip>
          <el-tag v-else :type="healthTagType(row.health_status)">{{ healthLabel(row.health_status) }}</el-tag>
          <small v-if="row.health_latency_ms" class="health-latency">{{ row.health_latency_ms }} ms</small>
          <small class="health-breakdown">
            TCP {{ probeLabel(row.health_tcp_status) }} · TLS {{ probeLabel(row.health_tls_status) }}
          </small>
        </template>
      </el-table-column>
      <el-table-column label="凭证" width="130">
        <template #default="{ row }">
          {{ row.uuid_masked || row.password_masked || row.username_masked || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="370" fixed="right">
        <template #default="{ row }">
          <el-button size="small" :loading="healthChecking === row.id" @click="checkHealth(row)">检测</el-button>
          <el-button size="small" @click="openUsage(row)">使用情况</el-button>
          <el-button size="small" @click="shareNode(row)">
            <el-icon><Share /></el-icon>
            {{ row.node_category === 'forwarded' ? '入站分享' : '分享' }}
          </el-button>
          <el-button v-if="row.node_category === 'external'" size="small" type="warning" @click="openForward(row)">
            转发
          </el-button>
          <el-button
            v-if="row.node_category === 'external'"
            size="small"
            type="primary"
            @click="openEdit(row)"
          >编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty-state">
          <p class="empty-state-title">还没有节点</p>
          <p class="empty-state-desc">同步上游订阅或导入外部节点后，这里会显示统一资源池。</p>
          <el-button type="primary" @click="openCreate">+ 导入外部节点</el-button>
        </div>
      </template>
      </el-table>
    </div>

    <el-dialog v-model="shareVisible" title="节点分享链接" width="620px" append-to-body>
      <div class="share-node-name">{{ shareNodeName }}</div>
      <el-input
        v-model="shareContent"
        type="textarea"
        :rows="4"
        readonly
        resize="none"
      />
      <template #footer>
        <el-button @click="shareVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyShareContent">复制链接</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="forwardVisible" title="创建 3x-ui 转发任务" width="560px" append-to-body>
      <div v-if="forwardNode" class="forward-source">
        <strong>{{ forwardNode.name }}</strong>
        <span>{{ forwardNode.node_code }} · {{ forwardNode.type }} · {{ forwardNode.server }}:{{ forwardNode.port }}</span>
      </div>
      <el-form label-width="110px">
        <el-form-item label="目标服务器" required>
          <el-select v-model="forwardForm.target_server_id" style="width: 100%" placeholder="选择已配置的 3x-ui 服务器">
            <el-option v-for="server in forwardServers" :key="server.id" :label="`${server.name} · ${server.domain || server.ip}`" :value="server.id">
              <span>{{ server.name }}</span><small class="option-meta">{{ server.domain || server.ip }} · {{ server.enabled ? '启用' : '停用' }}</small>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item v-if="forwardForm.forward_mode === 'inbound_outbound'" label="节点模板" required>
          <el-select v-model="forwardForm.template" style="width: 100%">
            <el-option label="VLESS TCP" value="vless_tcp" />
            <el-option label="VLESS WebSocket + TLS" value="vless_ws_tls" />
            <el-option label="VMess WebSocket + TLS" value="vmess_ws_tls" />
            <el-option label="Trojan TCP + TLS" value="trojan_tcp_tls" />
            <el-option label="Shadowsocks TCP" value="shadowsocks_tcp" />
          </el-select>
        </el-form-item>
        <el-form-item label="转发方式" required>
          <el-radio-group v-model="forwardForm.forward_mode">
            <el-radio-button label="port_forward">端口转发</el-radio-button>
            <el-radio-button label="inbound_outbound">新建入站 + 原始出站</el-radio-button>
          </el-radio-group>
          <div class="form-tip">端口转发直接把目标端口转到原始节点；入站出站模式会写入路由规则。</div>
        </el-form-item>
        <el-form-item label="入站备注">
          <el-input v-model="forwardForm.inbound_remark" maxlength="255" clearable placeholder="留空自动使用地区-IP" />
        </el-form-item>
        <el-form-item label="监听端口" required>
          <el-input-number v-model="forwardForm.listen_port" :min="1" :max="65535" placeholder="自动分配" />
          <div class="form-tip">留空时从 12900 开始按目标服务器已有任务顺序分配。</div>
        </el-form-item>
      </el-form>
      <el-alert title="确认后由后台任务调用 3x-ui，成功后会在资源池生成已转发节点。" type="info" :closable="false" />
      <template #footer>
        <el-button @click="forwardVisible = false">取消</el-button>
        <el-button type="primary" :loading="forwardSaving" @click="createForward">创建任务</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="forwardProgressVisible" title="3x-ui 转发进度" width="520px" append-to-body @closed="stopForwardProgressPolling">
      <div v-if="forwardProgressTask" class="forward-progress">
        <div class="forward-progress-head">
          <strong>任务 #{{ forwardProgressTask.id }}</strong>
          <el-tag :type="forwardTaskTagType(forwardProgressTask.status)">
            {{ forwardTaskLabel(forwardProgressTask.status) }}
          </el-tag>
        </div>
        <el-progress
          :percentage="forwardProgressTask.progress || 0"
          :status="forwardProgressStatus(forwardProgressTask)"
          :stroke-width="12"
        />
        <div class="forward-progress-meta">
          <span>{{ forwardProgressTask.stage || '等待后台处理' }}</span>
          <strong>{{ forwardProgressTask.progress || 0 }}%</strong>
        </div>
        <el-alert
          v-if="forwardProgressTask.status === 'failed'"
          title="转发任务失败"
          :description="forwardProgressTask.error_message || '请到 3x-ui 服务器页面查看详细信息并重试。'"
          type="error"
          :closable="false"
        />
        <el-alert
          v-else-if="forwardProgressTask.status === 'succeeded'"
          title="转发完成，已在资源池生成已转发节点"
          type="success"
          :closable="false"
        />
        <p v-else class="forward-progress-tip">后台正在处理，关闭窗口不会中断任务。</p>
      </div>
      <template #footer>
        <el-button @click="forwardProgressVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchForwardVisible" title="批量创建 3x-ui 转发任务" width="600px" append-to-body>
      <el-alert
        :title="`已选择 ${selected.length} 个节点，后台会为每个节点创建独立任务`"
        type="info"
        :closable="false"
        class="batch-forward-alert"
      />
      <el-form label-width="120px" class="batch-forward-form">
        <el-form-item label="目标服务器" required>
          <el-select v-model="batchForwardForm.target_server_id" style="width: 100%" placeholder="选择已配置的 3x-ui 服务器">
            <el-option v-for="server in forwardServers" :key="server.id" :label="`${server.name} · ${server.domain || server.ip}`" :value="server.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="batchForwardForm.forward_mode === 'inbound_outbound'" label="节点模板" required>
          <el-select v-model="batchForwardForm.template" style="width: 100%">
            <el-option label="VLESS TCP" value="vless_tcp" />
            <el-option label="VLESS WebSocket + TLS" value="vless_ws_tls" />
            <el-option label="VMess WebSocket + TLS" value="vmess_ws_tls" />
            <el-option label="Trojan TCP + TLS" value="trojan_tcp_tls" />
            <el-option label="Shadowsocks TCP" value="shadowsocks_tcp" />
          </el-select>
        </el-form-item>
        <el-form-item label="转发方式" required>
          <el-radio-group v-model="batchForwardForm.forward_mode">
            <el-radio-button label="port_forward">端口转发</el-radio-button>
            <el-radio-button label="inbound_outbound">新建入站 + 原始出站</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="入站备注">
          <el-input v-model="batchForwardForm.inbound_remark" maxlength="255" clearable placeholder="留空按每个节点地区-IP生成" />
        </el-form-item>
        <el-form-item label="端口范围" required>
          <el-input-number v-model="batchForwardForm.listen_port_start" :min="1" :max="65535" />
          <span class="range-separator">至</span>
          <el-input-number v-model="batchForwardForm.listen_port_end" :min="1" :max="65535" />
        </el-form-item>
      </el-form>
      <div class="form-tip">后台会自动跳过已占用端口；不符合外部节点要求的项目会单独返回失败原因。</div>
      <template #footer>
        <el-button @click="batchForwardVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchForwardSaving" @click="createBatchForward">创建批量任务</el-button>
      </template>
    </el-dialog>

    <el-pagination
      class="pagination"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="(value) => { page = value; load() }"
    />

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑节点' : '导入外部节点'" width="760px" append-to-body>
      <template v-if="!editing">
        <el-form label-width="120px" class="import-meta-form">
          <el-form-item label="来源备注">
            <el-input v-model="importNote" maxlength="2000" clearable placeholder="例如：供应商 A、客户提供、备用线路" />
          </el-form-item>
          <el-form-item label="资源到期时间">
            <el-date-picker v-model="importExpiresAt" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" clearable placeholder="留空表示长期有效" />
            <div class="form-tip">到期后不会再进入新订阅，已有客户线路也会显示为已到期。</div>
          </el-form-item>
        </el-form>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="链接导入" name="url">
          <el-input
            v-model="importUrlText"
            type="textarea"
            :rows="8"
            placeholder="每行粘贴一条节点链接，支持 vless:// vmess:// ss:// trojan:// anytls:// socks:// http:// hysteria:// hysteria2:// tuic://"
          />
          <div class="import-actions">
            <el-button type="primary" :loading="importing" @click="doImport('custom_url')">导入链接</el-button>
          </div>
          <div v-if="importResult" class="import-result">
            <div class="import-stats">
              <el-tag type="info">总数 {{ importResult.total }}</el-tag>
              <el-tag type="success">成功 {{ importResult.success }}</el-tag>
              <el-tag type="warning">重复 {{ importResult.duplicate }}</el-tag>
              <el-tag type="danger">失败 {{ importResult.failed }}</el-tag>
            </div>
            <ul v-if="importResult.failures.length" class="import-failures">
              <li v-for="failure in importResult.failures" :key="failure.index">
                第 {{ failure.index }} 条：{{ failure.reason }}
              </li>
            </ul>
          </div>
        </el-tab-pane>
        <el-tab-pane label="配置/订阅内容导入" name="config">
          <el-input
            v-model="importConfigText"
            type="textarea"
            :rows="8"
            placeholder="粘贴 Clash/Mihomo YAML、Base64 节点列表、VMess/V2Ray JSON 或 Sing-box JSON"
          />
          <div class="import-actions">
            <el-button type="primary" :loading="importing" @click="doImport('custom_import')">导入配置</el-button>
          </div>
          <div v-if="importResult" class="import-result">
            <div class="import-stats">
              <el-tag type="info">总数 {{ importResult.total }}</el-tag>
              <el-tag type="success">成功 {{ importResult.success }}</el-tag>
              <el-tag type="warning">重复 {{ importResult.duplicate }}</el-tag>
              <el-tag type="danger">失败 {{ importResult.failed }}</el-tag>
            </div>
            <ul v-if="importResult.failures.length" class="import-failures">
              <li v-for="failure in importResult.failures" :key="failure.index">
                第 {{ failure.index }} 条：{{ failure.reason }}
              </li>
            </ul>
          </div>
        </el-tab-pane>
        <el-tab-pane label="手动录入" name="manual">
          <el-form label-width="120px">
            <el-form-item label="名称">
              <el-input v-model="form.name" />
            </el-form-item>
            <el-form-item label="类型">
              <el-select v-model="form.type" style="width: 100%">
                <el-option v-for="option in protocolOptions" :key="option.value" :label="option.label" :value="option.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="服务器">
              <el-input v-model="form.server" />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="form.port" :min="1" :max="65535" />
            </el-form-item>
            <template v-if="form.type === 'vless'">
              <el-form-item label="UUID"><el-input v-model="form.uuid" /></el-form-item>
              <el-form-item label="传输"><el-input v-model="form.network" placeholder="tcp / ws" /></el-form-item>
              <el-form-item label="安全"><el-input v-model="form.security" placeholder="reality / tls" /></el-form-item>
              <el-form-item label="TLS"><el-switch v-model="form.tls" /></el-form-item>
              <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
              <el-form-item label="指纹"><el-input v-model="form.fingerprint" placeholder="chrome" /></el-form-item>
              <el-form-item label="Public Key"><el-input v-model="form.public_key" /></el-form-item>
              <el-form-item label="Short ID"><el-input v-model="form.short_id" /></el-form-item>
              <el-form-item label="Path"><el-input v-model="form.path" /></el-form-item>
              <el-form-item label="Host"><el-input v-model="form.host" /></el-form-item>
            </template>
            <template v-else-if="form.type === 'vmess'">
              <el-form-item label="UUID"><el-input v-model="form.uuid" /></el-form-item>
              <el-form-item label="加密"><el-input v-model="form.cipher" placeholder="auto" /></el-form-item>
              <el-form-item label="传输"><el-input v-model="form.network" placeholder="tcp / ws" /></el-form-item>
              <el-form-item label="TLS"><el-switch v-model="form.tls" /></el-form-item>
              <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
              <el-form-item label="Path"><el-input v-model="form.path" /></el-form-item>
              <el-form-item label="Host"><el-input v-model="form.host" /></el-form-item>
            </template>
            <template v-else-if="form.type === 'shadowsocks'">
              <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
              <el-form-item label="加密方式"><el-input v-model="form.cipher" placeholder="aes-256-gcm" /></el-form-item>
            </template>
            <template v-else-if="form.type === 'trojan'">
              <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
              <el-form-item label="传输"><el-input v-model="form.network" placeholder="tcp / ws" /></el-form-item>
              <el-form-item label="TLS"><el-switch v-model="form.tls" /></el-form-item>
              <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
              <el-form-item label="Path"><el-input v-model="form.path" /></el-form-item>
              <el-form-item label="Host"><el-input v-model="form.host" /></el-form-item>
            </template>
            <template v-else-if="form.type === 'anytls'">
              <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
              <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
              <el-form-item label="指纹"><el-input v-model="form.fingerprint" placeholder="chrome" /></el-form-item>
            </template>
            <template v-else-if="form.type === 'socks' || form.type === 'http'">
              <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
              <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
              <el-form-item label="TLS"><el-switch v-model="form.tls" /></el-form-item>
              <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
            </template>
            <template v-else-if="form.type === 'hysteria' || form.type === 'hysteria2'">
              <el-form-item label="认证密码"><el-input v-model="form.password" show-password /></el-form-item>
              <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
            </template>
            <template v-else-if="form.type === 'tuic'">
              <el-form-item label="UUID"><el-input v-model="form.uuid" /></el-form-item>
              <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
              <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
            </template>
            <el-form-item label="地区">
              <el-input v-model="form.country" placeholder="留空自动识别" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="form.note" type="textarea" :rows="2" maxlength="2000" show-word-limit placeholder="例如：主线路，适合日常使用" />
            </el-form-item>
            <el-form-item label="资源到期时间">
              <el-date-picker v-model="form.expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" clearable placeholder="留空表示长期有效" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="form.enabled" />
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
      </template>
      <el-form v-else label-width="120px">
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width: 100%">
            <el-option v-for="option in protocolOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="服务器">
          <el-input v-model="form.server" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input-number v-model="form.port" :min="1" :max="65535" />
        </el-form-item>
        <template v-if="form.type === 'vless'">
          <el-form-item label="UUID"><el-input v-model="form.uuid" /></el-form-item>
          <el-form-item label="传输"><el-input v-model="form.network" placeholder="tcp / ws" /></el-form-item>
          <el-form-item label="安全"><el-input v-model="form.security" placeholder="reality / tls" /></el-form-item>
          <el-form-item label="TLS"><el-switch v-model="form.tls" /></el-form-item>
          <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
          <el-form-item label="指纹"><el-input v-model="form.fingerprint" placeholder="chrome" /></el-form-item>
          <el-form-item label="Public Key"><el-input v-model="form.public_key" /></el-form-item>
          <el-form-item label="Short ID"><el-input v-model="form.short_id" /></el-form-item>
          <el-form-item label="Path"><el-input v-model="form.path" /></el-form-item>
          <el-form-item label="Host"><el-input v-model="form.host" /></el-form-item>
        </template>
        <template v-else-if="form.type === 'vmess'">
          <el-form-item label="UUID"><el-input v-model="form.uuid" /></el-form-item>
          <el-form-item label="加密"><el-input v-model="form.cipher" placeholder="auto" /></el-form-item>
          <el-form-item label="传输"><el-input v-model="form.network" placeholder="tcp / ws" /></el-form-item>
          <el-form-item label="TLS"><el-switch v-model="form.tls" /></el-form-item>
          <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
          <el-form-item label="Path"><el-input v-model="form.path" /></el-form-item>
          <el-form-item label="Host"><el-input v-model="form.host" /></el-form-item>
        </template>
        <template v-else-if="form.type === 'shadowsocks'">
          <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
          <el-form-item label="加密方式"><el-input v-model="form.cipher" placeholder="aes-256-gcm" /></el-form-item>
        </template>
        <template v-else-if="form.type === 'trojan'">
          <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
          <el-form-item label="传输"><el-input v-model="form.network" placeholder="tcp / ws" /></el-form-item>
          <el-form-item label="TLS"><el-switch v-model="form.tls" /></el-form-item>
          <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
          <el-form-item label="Path"><el-input v-model="form.path" /></el-form-item>
          <el-form-item label="Host"><el-input v-model="form.host" /></el-form-item>
        </template>
        <template v-else-if="form.type === 'anytls'">
          <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
          <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
          <el-form-item label="指纹"><el-input v-model="form.fingerprint" placeholder="chrome" /></el-form-item>
        </template>
        <template v-else-if="form.type === 'socks' || form.type === 'http'">
          <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
          <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
          <el-form-item label="TLS"><el-switch v-model="form.tls" /></el-form-item>
          <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
        </template>
        <template v-else-if="form.type === 'hysteria' || form.type === 'hysteria2'">
          <el-form-item label="认证密码"><el-input v-model="form.password" show-password /></el-form-item>
          <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
        </template>
        <template v-else-if="form.type === 'tuic'">
          <el-form-item label="UUID"><el-input v-model="form.uuid" /></el-form-item>
          <el-form-item label="密码"><el-input v-model="form.password" show-password /></el-form-item>
          <el-form-item label="SNI"><el-input v-model="form.sni" /></el-form-item>
        </template>
        <el-form-item label="地区">
          <el-input v-model="form.country" placeholder="留空自动识别" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" maxlength="2000" show-word-limit placeholder="例如：主线路，适合日常使用" />
        </el-form-item>
        <el-form-item label="资源到期时间">
          <el-date-picker v-model="form.expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" clearable placeholder="留空表示长期有效" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          v-if="editing || activeTab === 'manual'"
          type="primary"
          :loading="saving"
          @click="save"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="usageVisible" title="节点使用情况" width="820px" append-to-body>
      <div v-loading="usageLoading" class="usage-summary">
        <div class="usage-heading">
          <strong>{{ usageNodeName }}</strong>
          <span>{{ usageCode || '暂无编号' }}</span>
        </div>
        <el-alert
          v-if="usageData"
          :title="`删除影响：${usageData.package_count} 个套餐，${usageData.customer_subscription_count} 个客户订阅`"
          :type="usageData.customer_subscription_count ? 'warning' : 'info'"
          :closable="false"
        />
        <el-divider content-position="left">关联套餐</el-divider>
        <el-table v-if="usageData" :data="usageData.packages" max-height="240" empty-text="暂无套餐使用">
          <el-table-column prop="package_name" label="套餐" min-width="190" />
          <el-table-column label="命中方式" min-width="180"><template #default="{ row }"><el-tag v-for="type in row.match_types" :key="type" size="small" class="usage-tag">{{ type }}</el-tag></template></el-table-column>
          <el-table-column prop="customer_subscription_count" label="客户订阅数" width="120" />
        </el-table>
        <el-divider content-position="left">客户订阅</el-divider>
        <el-table v-if="usageData" :data="usageData.customer_subscriptions" max-height="260" empty-text="暂无客户订阅">
          <el-table-column prop="customer_name" label="客户" min-width="150" />
          <el-table-column prop="package_name" label="套餐" min-width="160" />
          <el-table-column prop="manager_username" label="负责经理" width="120"><template #default="{ row }">{{ row.manager_username || '未分配' }}</template></el-table-column>
          <el-table-column prop="status" label="状态" width="100" />
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  batchNodes,
  createNode,
  deleteNode,
  exportNode,
  getNodeUsage,
  getNode,
  checkNodeHealth,
  checkAllNodeHealth,
  importNodes,
  listThreeXUIServers,
  getThreeXUITask,
  createThreeXUIForwardTask,
  createThreeXUIForwardBatch,
  listNodes,
  listSources,
  updateNode,
  resolveNodeCountries
} from '../api'
import { formatApiDate } from '../utils/datetime'

const countryOptions = [
  '香港', '台湾', '日本', '韩国', '新加坡', '美国', '英国',
  '德国', '法国', '马来西亚', '墨西哥', '俄罗斯', '澳大利亚',
  '加拿大', '泰国', '越南', '印度', '荷兰', '印尼', '菲律宾',
  '中国', '巴西', '瑞士', '西班牙', '芬兰', '意大利', '挪威',
  '新西兰', '波兰', '葡萄牙', '瑞典', '土耳其', '乌克兰'
]

const protocolOptions = [
  { label: 'VLESS', value: 'vless' },
  { label: 'VMess', value: 'vmess' },
  { label: 'Shadowsocks', value: 'shadowsocks' },
  { label: 'Trojan', value: 'trojan' },
  { label: 'AnyTLS', value: 'anytls' },
  { label: 'SOCKS', value: 'socks' },
  { label: 'HTTP', value: 'http' },
  { label: 'Hysteria', value: 'hysteria' },
  { label: 'Hysteria2', value: 'hysteria2' },
  { label: 'TUIC', value: 'tuic' }
]

const rows = ref([])
const nodeScope = ref('all')
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const saving = ref(false)
const importing = ref(false)
const healthChecking = ref(null)
const healthCheckingAll = ref(false)
const countryResolving = ref(false)
const selected = ref([])
const sourceFilterOptions = ref([])
const route = useRoute()
const dialogVisible = ref(false)
const shareVisible = ref(false)
const shareContent = ref('')
const shareNodeName = ref('')
const usageVisible = ref(false)
const usageLoading = ref(false)
const usageData = ref(null)
const usageNodeName = ref('')
const usageCode = ref('')
const forwardVisible = ref(false)
const forwardSaving = ref(false)
const forwardProgressVisible = ref(false)
const forwardProgressTask = ref(null)
const batchForwardVisible = ref(false)
const batchForwardSaving = ref(false)
const forwardNode = ref(null)
const forwardServers = ref([])
const forwardForm = reactive({ target_server_id: null, template: 'vless_tcp', forward_mode: 'inbound_outbound', inbound_remark: '', listen_port: null })
const batchForwardForm = reactive({ target_server_id: null, template: 'vless_tcp', forward_mode: 'inbound_outbound', inbound_remark: '', listen_port_start: 12900, listen_port_end: 20000 })
let forwardProgressTimer = null
const editing = ref(null)
const activeTab = ref('url')
const importUrlText = ref('')
const importConfigText = ref('')
const importNote = ref('')
const importExpiresAt = ref(null)
const importResult = ref(null)
const filters = reactive({
  keyword: '',
  source_name: '',
  node_type: '',
  country: ''
})
const form = reactive({
  name: '',
  type: 'vless',
  server: '',
  port: 443,
  uuid: '',
  password: '',
  username: '',
  cipher: '',
  network: '',
  security: '',
  tls: false,
  sni: '',
  fingerprint: '',
  public_key: '',
  short_id: '',
  path: '',
  host: '',
  country: '',
  enabled: true,
  note: '',
  expires_at: null
})

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (nodeScope.value !== 'all') params.source_kind = nodeScope.value
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.source_name) params.source_name = filters.source_name
    if (filters.node_type) params.node_type = filters.node_type
    if (filters.country) params.country = filters.country
    const { data } = await listNodes(params)
    rows.value = data.items
    total.value = data.total
    selected.value = []
    await nextTick()
    document.querySelector('.notification-focus')?.scrollIntoView({ block: 'center' })
  } finally {
    loading.value = false
  }
}

async function resolveCountries() {
  countryResolving.value = true
  try {
    const { data } = await resolveNodeCountries({ limit: 100 })
    await load()
    const suffix = data.remaining ? '，还有节点等待下一轮处理' : ''
    ElMessage.success(`地区识别完成：成功 ${data.resolved} 个，跳过 ${data.skipped} 个，失败 ${data.failed} 个${suffix}`)
  } finally {
    countryResolving.value = false
  }
}

function changeNodeScope() {
  page.value = 1
  load()
}

function sourceLabel(row) {
  if (row.node_category === 'forwarded') return `已转发${row.forward_target_server_name ? ` · ${row.forward_target_server_name}` : ''}`
  return row.source_id === null ? '导入外部节点' : row.source_name
}

function tableRowClassName({ row }) {
  return String(row.id) === String(route.query.focus || '') ? 'notification-focus' : ''
}

function resetForm() {
  Object.assign(form, {
    name: '',
    type: 'vless',
    server: '',
    port: 443,
    uuid: '',
    password: '',
    username: '',
    cipher: '',
    network: '',
    security: '',
    tls: false,
    sni: '',
    fingerprint: '',
    public_key: '',
    short_id: '',
    path: '',
    host: '',
    country: '',
    enabled: true,
    note: '',
    expires_at: null
  })
}

function openCreate() {
  editing.value = null
  resetForm()
  activeTab.value = 'url'
  importUrlText.value = ''
  importConfigText.value = ''
  importNote.value = ''
  importExpiresAt.value = null
  importResult.value = null
  dialogVisible.value = true
}

async function openEdit(row) {
  editing.value = row
  const { data } = await getNode(row.id)
  Object.assign(form, {
    name: data.name,
    type: data.type,
    server: data.server,
    port: data.port,
    uuid: data.uuid || '',
    password: data.password || '',
    username: data.username || '',
    cipher: data.cipher || '',
    network: data.network || '',
    security: data.security || '',
    tls: !!data.tls,
    sni: data.sni || '',
    fingerprint: data.fingerprint || '',
    public_key: data.public_key || '',
    short_id: data.short_id || '',
    path: data.path || '',
    host: data.host || '',
    country: data.country || '',
    enabled: data.enabled,
    note: data.note || '',
    expires_at: data.expires_at || null
  })
  dialogVisible.value = true
}

async function doImport(sourceSubtype) {
  const content = sourceSubtype === 'custom_url' ? importUrlText.value : importConfigText.value
  if (!content.trim()) {
    ElMessage.warning('请先粘贴内容')
    return
  }
  importing.value = true
  try {
    const { data } = await importNodes({
      content,
      source_subtype: sourceSubtype,
      format: 'auto',
      note: importNote.value.trim() || null,
      expires_at: importExpiresAt.value || null
    })
    importResult.value = data
    ElMessage.success(`导入完成：成功 ${data.success}，重复 ${data.duplicate}，失败 ${data.failed}`)
    await load()
  } finally {
    importing.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const payload = { ...form }
    for (const key of Object.keys(payload)) {
      if (payload[key] === '') payload[key] = null
    }
    if (editing.value) {
      await updateNode(editing.value.id, payload)
    } else {
      await createNode(payload)
    }
    dialogVisible.value = false
    ElMessage.success('保存成功')
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  let impact = null
  try {
    const { data } = await getNodeUsage(row.id)
    impact = data
  } catch {
    ElMessage.error('无法读取节点影响范围，已取消删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除节点「${row.name}」？\n将影响 ${impact.package_count} 个套餐、${impact.customer_subscription_count} 个客户订阅。`,
      '删除确认',
      { type: impact.customer_subscription_count ? 'warning' : 'info', confirmButtonText: '确认删除' }
    )
  } catch {
    return
  }
  await deleteNode(row.id)
  ElMessage.success('已删除')
  await load()
}

async function openUsage(row) {
  usageNodeName.value = row.name
  usageCode.value = row.node_code || ''
  usageData.value = null
  usageVisible.value = true
  usageLoading.value = true
  try {
    const { data } = await getNodeUsage(row.id)
    usageData.value = data
  } finally {
    usageLoading.value = false
  }
}

async function shareNode(row) {
  const { data } = await exportNode(row.id)
  shareNodeName.value = data.name
  shareContent.value = data.content
  shareVisible.value = true
}

async function openForward(row) {
  forwardNode.value = row
  forwardForm.target_server_id = null
  forwardForm.template = 'vless_tcp'
  forwardForm.forward_mode = 'inbound_outbound'
  forwardForm.inbound_remark = ''
  forwardForm.listen_port = null
  forwardVisible.value = true
  try {
    const { data } = await listThreeXUIServers()
    forwardServers.value = data.filter((item) => item.enabled)
  } catch {
    forwardServers.value = []
  }
}

async function createForward() {
  if (!forwardNode.value || !forwardForm.target_server_id) {
    ElMessage.warning('请选择目标 3x-ui 服务器')
    return
  }
  forwardSaving.value = true
  try {
    const { data } = await createThreeXUIForwardTask({ source_node_id: forwardNode.value.id, ...forwardForm })
    forwardVisible.value = false
    startForwardProgressPolling(data)
    ElMessage.success('转发任务已创建，正在显示执行进度')
  } finally {
    forwardSaving.value = false
  }
}

function stopForwardProgressPolling() {
  if (forwardProgressTimer) {
    window.clearInterval(forwardProgressTimer)
    forwardProgressTimer = null
  }
}

function startForwardProgressPolling(task) {
  stopForwardProgressPolling()
  forwardProgressTask.value = task
  forwardProgressVisible.value = true
  if (['succeeded', 'failed'].includes(task.status)) return
  forwardProgressTimer = window.setInterval(async () => {
    try {
      const { data } = await getThreeXUITask(task.id)
      forwardProgressTask.value = data
      if (['succeeded', 'failed'].includes(data.status)) stopForwardProgressPolling()
    } catch {
      // 统一请求层负责提示错误，轮询下一次继续获取任务状态。
    }
  }, 2000)
}

function forwardTaskLabel(value) {
  return ({ pending: '待处理', running: '执行中', succeeded: '成功', failed: '失败' })[value] || value
}

function forwardTaskTagType(value) {
  return ({ pending: 'info', running: 'warning', succeeded: 'success', failed: 'danger' })[value] || 'info'
}

function forwardProgressStatus(task) {
  return ({ succeeded: 'success', failed: 'exception' })[task.status] || undefined
}

async function openBatchForward() {
  if (!selected.value.length) return
  batchForwardForm.target_server_id = null
  batchForwardForm.template = 'vless_tcp'
  batchForwardForm.forward_mode = 'inbound_outbound'
  batchForwardForm.inbound_remark = ''
  batchForwardForm.listen_port_start = 12900
  batchForwardForm.listen_port_end = 20000
  batchForwardVisible.value = true
  try {
    const { data } = await listThreeXUIServers()
    forwardServers.value = data.filter((item) => item.enabled)
  } catch {
    forwardServers.value = []
  }
}

async function createBatchForward() {
  if (!batchForwardForm.target_server_id) {
    ElMessage.warning('请选择目标 3x-ui 服务器')
    return
  }
  if (batchForwardForm.listen_port_end < batchForwardForm.listen_port_start) {
    ElMessage.warning('端口范围无效')
    return
  }
  batchForwardSaving.value = true
  try {
    const { data } = await createThreeXUIForwardBatch({
      source_node_ids: selected.value,
      ...batchForwardForm
    })
    batchForwardVisible.value = false
    const skipped = data.skipped?.length || 0
    ElMessage.success(`已创建 ${data.tasks.length} 个转发任务${skipped ? `，跳过 ${skipped} 个` : ''}`)
    selected.value = []
  } finally {
    batchForwardSaving.value = false
  }
}

async function checkHealth(row) {
  healthChecking.value = row.id
  try {
    const { data } = await checkNodeHealth(row.id)
    Object.assign(row, {
      health_status: data.status,
      health_checked_at: data.checked_at,
      health_latency_ms: data.latency_ms,
      health_detail: data.detail,
      health_tcp_status: data.tcp_status,
      health_tls_status: data.tls_status,
      health_tcp_latency_ms: data.tcp_latency_ms,
      health_tls_latency_ms: data.tls_latency_ms
    })
    ElMessage.success(`检测完成：${healthLabel(data.status)}${data.detail ? `，${data.detail}` : ''}`)
  } finally {
    healthChecking.value = null
  }
}

async function checkAllHealth() {
  try {
    await ElMessageBox.confirm(
      '将检测所有启用的资源池节点，节点数量较多时可能需要一些时间。确认继续吗？',
      '全部检测',
      { type: 'info', confirmButtonText: '开始检测', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  healthCheckingAll.value = true
  try {
    const { data } = await checkAllNodeHealth()
    ElMessage.success(`全部检测完成，共检测 ${data.checked} 个启用节点`)
    await load()
  } finally {
    healthCheckingAll.value = false
  }
}

async function copyShareContent() {
  try {
    await navigator.clipboard.writeText(shareContent.value)
    ElMessage.success('节点链接已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function batchAction(action) {
  const label = { enable: '启用', disable: '禁用', delete: '删除' }[action]
  if (action === 'delete' || action === 'disable') {
    let impacts
    try {
      impacts = await Promise.all(selected.value.map((id) => getNodeUsage(id)))
    } catch {
      ElMessage.error('无法读取节点影响范围，操作已取消')
      return
    }
    const packageIds = new Set(impacts.flatMap(({ data }) => data.packages.map((item) => item.package_id)))
    const subscriptionIds = new Set(impacts.flatMap(({ data }) => data.customer_subscriptions.map((item) => item.subscription_id)))
    try {
      await ElMessageBox.confirm(
        `确认${label}选中的 ${selected.value.length} 个节点？\n将影响 ${packageIds.size} 个套餐、${subscriptionIds.size} 个客户订阅。`,
        `批量${label}`,
        {
          type: subscriptionIds.size ? 'warning' : 'info',
          confirmButtonText: `确认${label}`
        }
      )
    } catch {
      return
    }
  }
  await batchNodes({ ids: selected.value, action })
  ElMessage.success(`已${label} ${selected.value.length} 个节点`)
  await load()
}

onMounted(() => {
  load()
  loadSourceFilterOptions()
})
onBeforeUnmount(stopForwardProgressPolling)

function formatTime(value) {
  return formatApiDate(value)
}

async function loadSourceFilterOptions() {
  const { data } = await listSources()
  sourceFilterOptions.value = data.items.map((item) => item.name)
}

function healthLabel(value) {
  return ({ healthy: '正常', degraded: '异常', offline: '离线', unknown: '待检测' })[value] || '未知'
}

function healthTagType(value) {
  return ({ healthy: 'success', degraded: 'warning', offline: 'danger', unknown: 'info' })[value] || 'info'
}

function probeLabel(value) {
  return ({ passed: '通过', failed: '失败', not_applicable: '不适用', unknown: '未知' })[value] || '未知'
}
</script>

<style scoped>
.spacer {
  flex: 1;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filters {
  margin-bottom: -18px;
}

.node-filters-card {
  margin-bottom: 16px;
  padding-bottom: 6px;
}

.node-scope-tabs {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 4px;
}

.node-scope-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.scope-hint {
  color: var(--app-text-muted);
  font-size: 12px;
}

.node-table-card {
  padding: 12px 16px 16px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.import-actions {
  margin: 12px 0;
}

.import-meta-form {
  margin-bottom: 4px;
}

.import-stats {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.import-failures {
  margin: 8px 0;
  padding-left: 20px;
  color: #dc2626;
  font-size: 12px;
}

.share-node-name {
  margin-bottom: 12px;
  color: var(--app-text-secondary);
}

.forward-source {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 18px;
  padding: 12px 14px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-card-soft);
}

.forward-source span,
.option-meta,
.form-tip {
  color: var(--app-text-muted);
  font-size: 12px;
}

.option-meta {
  float: right;
  margin-left: 18px;
}

.form-tip {
  margin-left: 12px;
}

.usage-heading {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 14px;
}

.usage-heading span {
  color: var(--app-text-muted);
  font-size: 12px;
}

.usage-tag {
  margin-right: 6px;
}

.health-latency {
  display: block;
  margin-top: 2px;
  color: var(--app-text-muted);
  font-size: 11px;
}

.health-breakdown {
  display: block;
  margin-top: 2px;
  color: var(--app-text-muted);
  font-size: 10px;
}

.forward-endpoint {
  display: block;
  margin-top: 3px;
  color: var(--app-text-muted);
  font-size: 11px;
}

.forward-progress-head,
.forward-progress-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.forward-progress-head {
  margin-bottom: 22px;
}

.forward-progress-meta {
  margin-top: 8px;
  color: var(--app-text-secondary);
  font-size: 12px;
}

.forward-progress-tip {
  margin: 18px 0 0;
  color: var(--app-text-muted);
  font-size: 12px;
}

@media (max-width: 768px) {
  .node-scope-tabs {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .node-filters-card {
    padding-bottom: 0;
  }

  .filters {
    margin-bottom: 0;
  }

  .filters .el-form-item {
    width: 100%;
    margin-right: 0;
  }

  .filters .el-input,
  .filters .el-select {
    width: 100%;
  }
}
</style>
