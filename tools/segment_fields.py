#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S3/S4 搜索字段守卫（此前被 search_company.py 引用但仓库缺失，2026-10-23 补齐）。

用途：确保扩量用的 keyword 只能是平台客群返回的 query_en 原文，
禁止本地自写英文/中文关键词、禁止把买家角色词塞进搜索词。
"""

import re


class SegmentFieldError(ValueError):
    """带机器码的字段错误，search_company.py 用它映射 _fail(code, reason)。"""

    def __init__(self, code: str, reason: str):
        super().__init__("%s: %s" % (code, reason))
        self.code = code
        self.reason = reason


_CJK = re.compile(r"[\u4e00-\u9fff]")
_ROLE_WORDS = ("buyer", "importer", "distributor", "wholesaler", "retailer")


def assert_search_keyword(query_en: object, raw: object = None) -> str:
    """校验 query_en 可直接作为 refine/company-list 的 keyword。

    - 必须是字符串且非空；
    - 禁止中文（搜索词应为平台返回的英文整句）；
    - 禁止换行/制表符；
    - 长度上限 300 字符（超过大概率是粘错内容）；
    - 若 raw 为 None 则以 query_en 自身作为原始值。
    """
    source = raw if raw is not None else query_en
    if not isinstance(source, str) or not source.strip():
        raise SegmentFieldError("E_SEGMENT_QUERY_EN_MISSING", "缺 query_en 原文；先跑 segments_infer 生成登记")
    text = source.strip()
    if _CJK.search(text):
        raise SegmentFieldError("E_SEGMENT_QUERY_EN_NOT_EN", "query_en 必须是平台返回的英文原文，不得中文自写")
    if "\n" in text or "\t" in text:
        raise SegmentFieldError("E_SEGMENT_QUERY_EN_INVALID", "query_en 含换行/制表符，请重新复制平台原文")
    if len(text) > 300:
        raise SegmentFieldError("E_SEGMENT_QUERY_EN_TOO_LONG", "query_en 超过 300 字符，疑似粘错内容")
    return text
