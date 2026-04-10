const ArtifactBucketModal = {
    components: {
        'input-stepper': InputStepper,
    },
    props: ['bucket', 'minioQuery'],
    data() {
        return {
            bucketData: {
                name: '',
                retention: 'days',
                expiration: 1,
                storage: null,
            },
            applyClicked: false,
            isValidBucket: false,
            isLoading: false,
        }
    },
    mounted() {
        $('#selectRetention').on('change', (e) => {
            this.bucketData.retention = e.target.value;
        })
    },
    watch: {
        bucketData: {
            handler: function () {
                this.$nextTick(() => {
                    const arr = []
                    $('#bucketFields .need-validation').each(function (index, cell) {
                        arr.push(cell.getAttribute('data-valid'));
                    })
                    this.isValidBucket = arr.every(elem => elem === 'true')
                });
            },
            deep: true
        }
    },
    methods: {
        setYear(val) {
            this.bucketData.expiration = val;
        },
        saveBucket() {
            this.applyClicked = true;
            const api_url = this.$root.build_api_url('artifacts', 'buckets')
            if (this.isValidBucket) {
                this.isLoading = true;
                fetch(`${api_url}/${getSelectedProjectId()}${this.minioQuery}`,{
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', dataType: 'json'},
                    body: JSON.stringify({
                        "name": this.bucketData.name,
                        "expiration_measure": (this.bucketData.retention).toLowerCase(),
                        "expiration_value": String(this.bucketData.expiration),
                    })
                }).then((response) => {
                    if (response.status === 200) {
                        return response.json();
                    } else if (response.status === 400){
                        throw new Error('Bucket\'s name is exist!');
                    }
                }).then(data => {
                    this.isLoading = false;
                    this.applyClicked = false;
                    this.bucketData.name = '';
                    $('#bucketModal').modal('hide');
                    this.$emit('refresh-bucket', data.id);
                    showNotify('SUCCESS', 'Bucket created.');
                }).catch(err => {
                    this.isLoading = false;
                    showNotify('ERROR', err);
                })
            }
        },
        hasError(value) {
            return value.length > 0;
        },
        showError(value) {
            return this.applyClicked ? value.length > 0 : true;
        },
    },
    template: `
        <div class="modal modal-small fixed-left fade shadow-sm" tabindex="-1" role="dialog" id="bucketModal">
            <div class="modal-dialog modal-dialog-aside" role="document">
                <div class="modal-content">
                    <div class="modal-header">
                        <div class="row w-100">
                            <div class="col">
                                <h2>Create bucket</h2>
                            </div>
                            <div class="col-xs d-flex">
                                <button type="button" class="btn  btn-secondary mr-2" data-dismiss="modal" aria-label="Close">
                                    Cancel
                                </button>
                                <button type="button" 
                                    class="btn btn-basic d-flex align-items-center"
                                    @click="saveBucket"
                                >Save<i v-if="isLoading" class="preview-loader__white ml-2"></i></button>
                            </div>
                        </div>
                    </div>
                    <div class="modal-body">
                        <div class="section">
                            <div class="row" id="bucketFields">
                                <div class="custom-input need-validation mb-3 w-100" :class="{'invalid-input': !showError(bucketData.name)}"
                                    :data-valid="hasError(bucketData.name)">
                                    <label for="BucketName" class="font-weight-bold mb-1">Name</label>
                                    <input
                                        id="BucketName"
                                        type="text"
                                        v-model="bucketData.name"
                                        placeholder="Bucket name">
                                </div>
                                <div class="row align-items-end mb-3">
                                    <div class="custom-input mr-2">
                                        <label class="font-weight-bold mb-0">Retention policy</label>
                                        <p class="custom-input_desc mb-2">Description</p>
                                        <select class="selectpicker bootstrap-select__b" id="selectRetention" data-style="btn">
                                            <option>Days</option>
                                            <option>Years</option>
                                            <option>Months</option>
                                            <option>Weeks</option>
                                        </select>
                                    </div>
                                    <div>
                                        <input-stepper 
                                            :default-value="1"
                                            @change="setYear"
                                        ></input-stepper>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `
}
