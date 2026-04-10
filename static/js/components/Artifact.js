const Artifact = {
    // props: ['session'],
    components: {
        'artifact-bucket-modal': ArtifactBucketModal,
        'artifact-bucket-update-modal': ArtifactBucketUpdateModal,
        'artifact-files-table': ArtifactFilesTable,
        'artifact-bucket-aside': ArtifactBucketAside,
        'artifact-confirm-modal': ArtifactConfirmModal,
    },
    data() {
        return {
            selectedBucket: {
                name: null,
            },
            selectedBucketRowIndex: null,
            loadingDelete: false,
            isInitDataFetched: false,
            showConfirm: false,
            bucketCount: 0,
            checkedBucketsList: [],
            projectIntegrations: [],
            selectedIntegration: undefined,
            minioQuery: ''
        }
    },
    computed: {
        default_integration() {
            return this.projectIntegrations.find(item => item.is_default)
        },
    },
    mounted() {
        $(document).on('vue_init', () => {
            const vm = this;
            this.fetchS3Integrations()
            this.fetchBuckets().then(data => {
                $("#bucket-table").bootstrapTable('append', data.rows);
                this.setBucketEvent(data.rows)
                this.bucketCount = data.rows.length;
                this.isInitDataFetched = true;
                if (data.rows.length > 0) {
                    this.selectFirstBucket();
                }
                return data.rows
            }).then((rows) => {
                if (rows.length > 0) {
                    this.fetchArtifacts(vm.selectedBucket.name).then(data => {
                        $("#artifact-table").bootstrapTable('append', data.rows);
                        $('#filesRetentionPolicy')
                            .text(`${data.retention_policy?.expiration_value} ${data.retention_policy?.expiration_measure}`)
                    })
                }
            })
        })
    },
    methods: {
        setBucketEvent(bucketList) {
            const vm = this;
            $('#bucket-table').on('click', 'tbody tr:not(.no-records-found)', function (event) {
                const selectedUniqId = this.getAttribute('data-uniqueid');
                vm.selectedBucket = bucketList.find(row => row.id === selectedUniqId);
                $(this).addClass('highlight').siblings().removeClass('highlight');
                vm.refreshArtifactTable(vm.selectedBucket.name);
            });
        },
        async fetchS3Integrations() {
            const api_url = this.$root.build_api_url('integrations', 'integrations')
            const params = '?' + new URLSearchParams({name: 's3_integration'})
            const res = await fetch(`${api_url}/${this.$root.project_id}${params}`, {
                method: 'GET',
            })
            if (res.ok) {
                this.projectIntegrations = await res.json()
                this.selectedIntegration = this.get_integration_value(this.default_integration)
                this.$nextTick(() => {
                    $('#selector_integration').val(this.selectedIntegration)
                    $('#selector_integration').selectpicker('refresh')
                })
            } else {
                console.warn('Couldn\'t fetch S3 integrations. Resp code: ', res.status)
            }
        },
        async fetchArtifacts(bucket) {
            const api_url = this.$root.build_api_url('artifacts', 'artifacts')
            const res = await fetch(`${api_url}/${this.$root.project_id}/${bucket}${this.minioQuery}`, {
                method: 'GET',
            })
            return res.json();
        },
        async fetchBuckets() {
            const api_url = this.$root.build_api_url('artifacts', 'buckets')
            const res = await fetch(`${api_url}/${this.$root.project_id}${this.minioQuery}`, {
                method: 'GET',
            })
            return res.json();
        },
        refreshArtifactTable(bucked) {
            this.fetchArtifacts(bucked).then(data => {
                $('#filesRetentionPolicy')
                    .text(`${data.retention_policy?.expiration_value} ${data.retention_policy?.expiration_measure}`)
                $("#artifact-table").bootstrapTable('load', data.rows);
            })
        },
        updateFilesRetentionPolicy(policy) {
            $('#filesRetentionPolicy')
                .text(`${policy.expiration} ${policy.retention}`)
        },
        refreshBucketTable(bucketId = null) {
            this.fetchBuckets().then(data => {
                $("#bucket-table").bootstrapTable('load', data.rows);
                this.bucketCount = data.rows.length;
                $('#bucket-table').off('click', 'tbody tr:not(.no-records-found)')
                this.setBucketEvent(data.rows);
                if (bucketId) {
                    this.selectedBucket = data.rows.find(row => row.id === bucketId);
                    $('#bucket-table').find(`[data-uniqueid='${bucketId}']`).addClass('highlight');
                    this.refreshArtifactTable(this.selectedBucket.name)
                } else {
                    this.selectFirstBucket();
                }
            })
        },
        getBucketNameCallIndex(row) {
            let bucketNameCallIndex;
            row.childNodes.forEach((node, index) => {
                const isBucketNameCell = node.className.split(' ').includes('bucket-name');
                if (isBucketNameCell) {
                    bucketNameCallIndex = index;
                }
            })
            return bucketNameCallIndex;
        },
        selectFirstBucket() {
            const vm = this;
            $('#bucket-table tbody tr').each(function (i, item) {
                if (i === 0) {
                    const firstRow = $(item);
                    firstRow.addClass('highlight');
                    vm.selectedBucketRowIndex = 0;
                    vm.selectedBucket = $('#bucket-table').bootstrapTable('getData')[0];
                }
            })
        },
        refresh(newSize) {
            this.selectedBucket.size = newSize;
            $('#bucket-table').bootstrapTable('updateRow', {
                index: this.selectedBucketRowIndex,
                row: {
                    size: newSize,
                }
            })
            $('#bucket-table').find(`[data-uniqueid='${this.selectedBucket.id}']`).addClass('highlight');
            this.refreshArtifactTable(this.selectedBucket.name, true);
        },
        switcherDeletingBucket() {
            this.bucketDeletingType === 'single' ? this.deleteBucket() : this.deleteSelectedBuckets();
        },
        deleteBucket() {
            this.loadingDelete = true;
            const api_url_part = this.$root.build_api_url('artifacts', 'buckets')
            let url = `${api_url_part}/${this.$root.project_id}`
            this.minioQuery ? url += `${this.minioQuery}&name=${this.selectedBucket.name}` : url += `?name=${this.selectedBucket.name}`
            fetch(url, {
                method: 'DELETE',
            }).then((data) => {
                this.refreshBucketTable();
            }).finally(() => {
                this.loadingDelete = false;
                this.showConfirm = !this.showConfirm;
                showNotify('SUCCESS', 'Bucket delete.');
            })
        },
        deleteSelectedBuckets() {
            const api_url = this.$root.build_api_url('artifacts', 'buckets')
            const selectedBucketList = $("#bucket-table").bootstrapTable('getSelections')
                .map(bucket => bucket.name.toLowerCase());       
            const urls = selectedBucketList.map(name => {
                if (this.minioQuery) {
                    return `${api_url}/${this.$root.project_id}${this.minioQuery}&name=${name}`
                } else {
                    return`${api_url}/${this.$root.project_id}?name=${name}`
                }     
            })
            this.loadingDelete = true;
            let chainPromises = Promise.resolve();
            urls.forEach((url) => {
                chainPromises = chainPromises.then(() => fetch(url, {method: 'DELETE'}))
            });
            chainPromises.finally(() => {
                this.refreshBucketTable();
                this.loadingDelete = false;
                this.showConfirm = !this.showConfirm;
                showNotify('SUCCESS', 'Buckets delete.');

            })
        },
        openConfirm(type) {
            this.bucketDeletingType = type;
            this.showConfirm = !this.showConfirm;
        },
        updateBucketList(buckets) {
            this.checkedBucketsList = buckets;
        },
        get_integration_value(integration) {
            return `${integration?.id}#${integration?.project_id}`
        },
        is_default_integration(integration_id, is_local) {
            return this.default_integration.id === integration_id &&
                !!this.default_integration.project_id === is_local
        },
        updateIntegration(integration_value) {
            const integration_id = parseInt(integration_value?.split('#')[0])
            const is_local = integration_value?.split('#')[1] !== 'null'
            if (this.is_default_integration(integration_id, is_local)) {
                this.minioQuery = '';
            }
            else {
                this.minioQuery = '?' + new URLSearchParams({integration_id, is_local});
            }
            this.fetchBuckets().then(data => {
                $("#bucket-table").bootstrapTable('load', data.rows);
                this.bucketCount = data.rows.length;
                $('#bucket-table').off('click', 'tbody tr:not(.no-records-found)')
                if (data.rows.length > 0) {
                    this.setBucketEvent(data.rows);
                    this.selectFirstBucket();
                    this.refreshArtifactTable(this.selectedBucket.name)
                }
            })
        },
    },
    template: ` 
        <main class="d-flex align-items-start justify-content-center mb-3">
            <artifact-bucket-aside
                @open-confirm="openConfirm"
                @update-bucket-list="updateBucketList"
                @update-selected-integration="updateIntegration"
                :checked-buckets-list="checkedBucketsList"
                :bucket-count="bucketCount"
                :selected-bucket="selectedBucket"
                :selected-bucket-row-index="selectedBucketRowIndex"
                :is-init-data-fetched="isInitDataFetched"
                :project-integrations="projectIntegrations"
                :selected-integration="selectedIntegration"
                :minio-query="minioQuery">
            </artifact-bucket-aside>
            <artifact-files-table
                @register="$root.register"
                instance_name="artifactFiles"
                :selected-bucket="selectedBucket"
                :minio-query="minioQuery"
                @refresh="refresh">
            </artifact-files-table>
            <artifact-bucket-modal
                :minio-query="minioQuery"
                @refresh-bucket="refreshBucketTable">
            </artifact-bucket-modal>
            <artifact-bucket-update-modal
                @refresh-policy="updateFilesRetentionPolicy"
                :selected-bucket="selectedBucket"
                :minio-query="minioQuery">
            </artifact-bucket-update-modal>
            <artifact-confirm-modal
                v-if="showConfirm"
                @close-confirm="openConfirm"
                :loading-delete="loadingDelete"
                @delete-bucket="switcherDeletingBucket">
            </artifact-confirm-modal>
        </main>
    `
};

register_component('artifact', Artifact);
