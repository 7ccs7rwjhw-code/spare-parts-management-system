from django import forms
from django.contrib.auth import get_user_model
from .models import Batch, Item
from .excel import FIELDS, HEADERS


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ["year", "month", "kind"]
        labels = {"year": "年份", "month": "月份", "kind": "申请类别"}


class ItemForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput, initial=1)

    class Meta:
        model = Item
        fields = [
            "new_code",
            "old_code",
            "description",
            "category",
            "equipment",
            "brand",
            "location",
            "unit",
            "active",
            "verified",
        ]
        labels = {
            "new_code": "新料号",
            "old_code": "旧料号",
            "description": "描述",
            "category": "分类",
            "equipment": "设备",
            "brand": "品牌",
            "location": "位置",
            "unit": "单位",
            "active": "启用",
            "verified": "已人工核验",
        }


class LineForm(forms.Form):
    lock_version = forms.IntegerField(widget=forms.HiddenInput)
    item = forms.ModelChoiceField(
        queryset=Item.objects.filter(active=True),
        required=False,
        label="关联配件（可留空待建档）",
    )
    unit = forms.CharField(
        max_length=30, required=False, label="单位（原件没有明确单位时须人工确认）"
    )
    confirmed = forms.BooleanField(
        required=False, label="已确认本行数量、单位及来源字段"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, title in zip(FIELDS, HEADERS):
            self.fields[key] = forms.CharField(
                label=title, required=key == "material_description", max_length=3000
            )


class UploadForm(forms.Form):
    file = forms.FileField(label="XLSX文件")
    catalog = forms.BooleanField(label="基础资料导入", required=False)


class ConfirmForm(forms.Form):
    sheet = forms.CharField(label="工作表名称")
    year = forms.IntegerField(min_value=2000, max_value=2100, label="人工确认年份")
    month = forms.IntegerField(min_value=1, max_value=12, label="人工确认月份")
    requester = forms.ModelChoiceField(
        queryset=get_user_model().objects.filter(is_active=True), label="实际申请人"
    )
    department = forms.CharField(max_length=100, label="归属部门")
    reason = forms.CharField(widget=forms.Textarea, label="月份/异常确认依据")
    factory_stock = forms.ChoiceField(
        required=False,
        choices=[("", "非18列无需选择"), ("12", "M库存"), ("14", "O库存")],
        label="18列表库存映射",
    )
    outstanding_qty = forms.ChoiceField(
        required=False,
        choices=[("", "非18列无需选择"), ("11", "L未交"), ("13", "N未交")],
        label="18列表未交映射",
    )


class CopyForm(forms.Form):
    year = forms.IntegerField(min_value=2000, max_value=2100)
    month = forms.IntegerField(min_value=1, max_value=12)
    lock_version = forms.IntegerField(widget=forms.HiddenInput)


class BindForm(forms.Form):
    lock_version = forms.IntegerField(widget=forms.HiddenInput)
    item = forms.ModelChoiceField(
        queryset=Item.objects.filter(active=True), label="关联到配件"
    )
