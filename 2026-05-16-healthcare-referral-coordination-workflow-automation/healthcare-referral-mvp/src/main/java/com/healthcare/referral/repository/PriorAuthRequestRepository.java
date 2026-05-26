package com.healthcare.referral.repository;

import com.healthcare.referral.domain.entity.PriorAuthRequest;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface PriorAuthRequestRepository extends JpaRepository<PriorAuthRequest, Long> {

    List<PriorAuthRequest> findByReferralId(Long referralId);

    Optional<PriorAuthRequest> findByReferralIdAndStatus(Long referralId, String status);
}